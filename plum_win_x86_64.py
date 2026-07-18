import sys

def is_integer(token):
    try:
        int(token)
        return True
    except ValueError:
        return False
    
def is_float(token):
    try:
        float(token)
        return True
    except ValueError:
        return False

class Win64ABI:
    ARG_REGS = [
        { 1 : "cl",  2 : "cx",  4 : "ecx", 8 : "rcx" },
        { 1 : "dl",  2 : "dx",  4 : "edx", 8 : "rdx" },
        { 1 : "r8b", 2 : "r8w", 4 : "r8d", 8 : "r8"  },
        { 1 : "r9b", 2 : "r9w", 4 : "r9d", 8 : "r9"  },
    ]

    def argument_reg(self, index: int, size: int) -> str:
        return self.ARG_REGS[index][size]

    def push_reg(self, index: int) -> str:
        return self.ARG_REGS[index][8]

class Generator:
    tokens: list                    # List of tokens
    str_lits: list                  # String literals extracted earlier
    tok_len: int = 0                # Length of 'tokens'
    tok_iter: int = 0               # Iterator through 'tokens'

    current_stack_depth: int = 0    # Temporary/Current scope stack depth

    procedures: list = []           # List of procedure names
    
    current_procedure: str = ""     # Current procedure name
    callee_arg_count: int = -1      # Callee arg count for variadics
    procedure_params: dict = {}     # List of procedures' parameters
    procedure_return: dict = {}     # List of procedures' return values

    procedure: str = ""             # Current procedure code
    
    if_counter: int = 0             # If counter for labels
    while_counter: int = 0          # While counter for labels
    control_stack: list = []        # Control stack for branches
    
    string_pool: dict = {}          # Holds all string literals

    bss_section: list = []          # BSS Data section
    statics: dict = {}              # Static variables [name] = type

    abi: Win64ABI                   # Holds Windows 64 ABI-specific details
    stack_allocation: int = 32      # Holds the amount to allocate and reset (bytes)

    program: str = ""               # Holds compiled program when done

    def __init__(self, tokens, str_literals):
        self.tok_len = len(tokens)
        self.tokens = tokens
        self.str_lits = str_literals
        self.abi = Win64ABI()
        pass

    def size_of(type) -> int:
        match type:
            case "[byte4]":
                return 4
            case "qword":
                return 8
            case "dword":
                return 4
            case "word":
                return 2
            case "byte":
                return 1
            case "ptr":
                return 8
            case "double":
                return 8
            case "float":
                return 8
            case _:
                print(f"Unknown type for static: {type}")
                sys.exit(1)

    def advance(self):
        self.tok_iter += 1
    
    def current(self) -> str:
        if self.tok_iter >= self.tok_len:
            return None
        return self.tokens[self.tok_iter]
    
    def next(self) -> str:
        self.tok_iter += 1
        if self.tok_iter >= self.tok_len:
            return None
        return self.tokens[self.tok_iter]

    def program_comment(self, comment: str) -> str:
        self.program += f"#    {comment}\n"

    def comment(self, comment: str):
        self.procedure += f"    #    {comment}\n"

    def tag(self, tag: str):
        self.program += f"    {tag}\n"

    def symbol(self, symbol: str):
        self.program += f"\"{symbol}\":\n"
    
    def inst(self, op, operand):
        width = 8
        self.procedure += f"    {op:<{width}}{operand}\n"
    
    def hijack(self, code):
        self.procedure += f"    {code}\n"

    def if_branch(self):
        self.procedure += f".IF_BRANCH_{self.if_counter}:"
        self.control_stack.append(("I", self.if_counter, self.current_stack_depth))
        self.if_counter += 1
    
    def else_branch(self):
        if not self.control_stack or self.control_stack[-1][0] != 'I':
            print(f"Compilation Error: Unexpected 'else', missing associated 'if'")
            sys.exit(1)
        
        block_type, block_id, saved_depth = self.control_stack[-1]

        if self.current_stack_depth > saved_depth:
            self.comment("Else: Auto-dropping")
            self.inst("add", f"sp, sp, #{(self.current_stack_depth - saved_depth) * 8}")
        
        self.current_stack_depth = saved_depth
        
        self.inst("b", f".END_BRANCH_{block_id}")
        self.procedure += f".ELSE_BRANCH_{block_id}:\n"
        self.comment("Else-branch:")

    def while_branch(self):
        self.procedure += f".WHILE_START_{self.while_counter}:"
        self.control_stack.append(("W", self.while_counter, self.current_stack_depth))
        self.while_counter += 1
    
    def do(self):
        block_type, block_id, saved_depth = self.control_stack.pop()

        match block_type:
            case 'I':
                self.pop("x0")
                self.inst("cmp", "x0, #0")
                self.inst("b.eq", f".ELSE_BRANCH_{block_id}")
                self.comment("Then-branch:")
            case 'W':
                self.pop("x0")
                self.inst("cmp", "x0, #0")
                self.inst("b.eq", f".WHILE_END_{block_id}")
            case _:
                print(f"Implementation Error: Unknown value in control_stack")
                sys.exit(1)
        
        self.current_stack_depth -= 1
        self.control_stack.append((block_type, block_id, self.current_stack_depth))

    def end(self):
        block_type, block_id, saved_depth = self.control_stack.pop()

        if self.current_stack_depth > saved_depth:
            self.comment("End: Auto-dropping")
            self.inst("add", f"sp, sp, #{(self.current_stack_depth - saved_depth) * 8}")
            self.current_stack_depth = saved_depth
        
        match block_type:
            case 'I':
                self.procedure += f".END_BRANCH_{block_id}:\n"
            case 'W':
                self.inst("b", f".WHILE_START_{block_id}")
                self.procedure += f".WHILE_END_{block_id}:\n"
            case _:
                print(f"Implementation Error: Unknown value in control_stack")
                sys.exit(1)

    def reserve(self, bytes: int):
        self.inst("sub", f"rsp, {bytes}")
    
    def resign(self, bytes: int):
        self.inst("add", f"rsp, {bytes}")

    def peek(self, reg: str):
        self.inst("mov", f"rsp, {reg}")

    def pop(self, reg: str):
        self.inst("pop", f"{reg}")

    def push(self, reg: str):
        self.inst("push", f"{reg}")
    
    def push_arg(self, index: int):
        reg = self.abi.push_reg(index)
        self.inst("push", f"{reg}")

    def expect_stack(self, count: int):
        if self.current_stack_depth < count:
            print(f"Compilation Error: '{self.current()}' expects at least {count} elements on the stack, got: {self.current_stack_depth}")
            sys.exit(1)

    def gen_asm(self):
        prev = ""
        curr = self.current()

        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            self.comment(curr)
            
            match curr:
                case "intrinsic__printf":
                    self.pop("rax")
                    self.reserve(32)
                    self.inst("call", "\"printf\"")
                    self.resign(32)
                    self.current_stack_depth -= 2
                    
                case "intrinsic__printf_ln":
                    self.pop("rax")
                    self.reserve(32)
                    self.inst("call", "\"printf\"")
                    self.resign(32)
                    
                    self.inst("mov", "rax, 10") # 10 is '\n'
                    self.reserve(32)
                    self.inst("call", "\"putchar\"")
                    self.resign(32)
                    self.current_stack_depth -= 2
                    
                case "intrinsic__scanf":
                    self.pop("rax")
                    self.reserve(32)
                    self.inst("call", "\"scanf\"")
                    self.resign(32)
                    self.current_stack_depth -= 2
                    
                case "dup":
                    self.expect_stack(1)
                    self.peek("rax")
                    self.push("rax")
                    self.current_stack_depth += 1
                    
                case "drop":
                    self.expect_stack(1)
                    self.inst("add", "rsp, 8")
                    self.current_stack_depth -= 1
                    
                case "swap":
                    self.expect_stack(2)
                    self.peek("rax")
                    self.inst("mov", "rcx, [rsp + 8]")
                    self.inst("mov", "[rsp], rcx")
                    self.inst("mov", "[rsp + 8], rax")

                case "rot":
                    self.expect_stack(3)
                    self.comment("[a, b, c] --> [b, c, a]")
                    self.peek("rax")
                    self.inst("mov", "rcx, [rsp + 8]")
                    self.inst("mov", "rdx, [rsp + 16]")
                    self.inst("mov", "[rsp + 16], rcx")
                    self.inst("mov", "[rsp + 8], rax")
                    self.inst("mov", "[rsp], rdx")

                case "over":
                    self.expect_stack(2)
                    self.inst("mov", "rax, [rsp + 8]")
                    self.push("rax")
                    self.current_stack_depth += 1
                    
                case "pick":
                    self.expect_stack(1)
                    self.pop("rax")
                    # x86 SIB addressing makes scaling by 8 easy
                    self.inst("mov", "rdx, [rsp + rax*8]")
                    self.push("rdx")

                case "alloc":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("shl", "rax, 3") # Shift left by 3 to multiply by 8
                    self.reserve(32)
                    self.inst("call", "\"malloc\"")
                    self.resign(32)
                    self.push("rax")

                case "free":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.reserve(32)
                    self.inst("call", "\"free\"")
                    self.resign(32)
                    self.current_stack_depth -= 1
                    
                case "exit":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("call", "\"exit\"")
                    self.current_stack_depth -= 1

                case ".":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("mov", "rax, [rax]") # Dereference address
                    self.push("rax")

                case "[]":
                    self.expect_stack(2)
                    self.pop("rax") # Index
                    self.pop("rcx") # Base array pointer
                    self.inst("mov", "rax, [rcx + rax*8]")
                    self.push("rax")
                    self.current_stack_depth -= 1

                case "=":
                    self.expect_stack(2)
                    self.pop("rax") # Value
                    self.pop("rcx") # Target address
                    self.inst("mov", "[rcx], rax")
                    self.current_stack_depth -= 2

                case "[]=":
                    self.expect_stack(3)
                    self.pop("rax") # Value
                    self.pop("rcx") # Index
                    self.pop("rdx") # Base pointer
                    self.inst("mov", "[rdx + rcx*8]", "rax")
                    self.current_stack_depth -= 3

                case "if":
                    self.if_branch()
                case "while":
                    self.while_branch()
                case "do":
                    self.do()
                case "else":
                    self.else_branch()

                case "return":
                    # SET self.stack_allocation to the needed amount

                    type = self.procedure_return[self.current_procedure]
                    if (type == "float" or type == "double"):
                        print("Returning floats is not implemented yet!")
                        sys.exit(1)
                    else:
                        self.pop("rax")      # Return value goes into rax
                        self.inst("mov", "rsp, rbp") # Tear down stack frame
                        self.inst("add", f"rsp, {self.stack_allocation}")
                        self.inst("pop", "rbp")
                        self.inst("ret", "")

                case "end":
                    # SET self.stack_allocation to the needed amount

                    if len(self.control_stack) > 0:
                        self.end()
                    else:
                        type = self.procedure_return[self.current_procedure]
                        if type == 0 and prev != "return":
                            self.inst("mov", "rax, 0")
                            self.inst("mov", "rsp, rbp")
                            self.inst("add", f"rsp, {self.stack_allocation}")
                            self.inst("pop", "rbp")
                            self.inst("ret", "")
                        return

                case "++":
                    self.pop("rax")
                    self.inst("inc", "rax")
                    self.push("rax")
                case "--":
                    self.pop("rax")
                    self.inst("dec", "rax")
                    self.push("rax")
                case "+":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("add", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "-":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("sub", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "*":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("imul", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "/":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("cqo", "") # Sign-extend rax into rdx:rax for idiv
                    self.inst("idiv", "rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "%":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("cqo", "")
                    self.inst("idiv", "rcx")
                    self.push("rdx") # Remainder goes into rdx
                    self.current_stack_depth -= 1
                case "&":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("and", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "|":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("or", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "^":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("xor", "rax, rcx")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case "~":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("not", "rax")
                    self.push("rax")
                case "neg":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("neg", "rax")
                    self.push("rax")
                case "<<":
                    self.expect_stack(2)
                    self.pop("rcx") # Shift count must be in cl/rcx on x86
                    self.pop("rax")
                    self.inst("shl", "rax, cl")
                    self.push("rax")
                    self.current_stack_depth -= 1
                case ">>":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("sar", "rax, cl")
                    self.push("rax")
                    self.current_stack_depth -= 1

                # --- Comparisons ---
                case "<" | ">" | "==" | "!=" | "<=" | ">=":
                    self.expect_stack(2)
                    self.pop("rcx")
                    self.pop("rax")
                    self.inst("cmp", "rax, rcx")
                    
                    # Determine setcc condition instruction suffix
                    cond_map = {"<": "l", ">": "g", "==": "e", "!=": "ne", "<=": "le", ">=": "ge"}
                    suffix = cond_map[curr]
                    
                    self.inst(f"set{suffix}", "al")
                    self.inst("movzx", "rax, al") # Clear upper bits of rax
                    self.push("rax")
                    self.current_stack_depth -= 1

                case "[hijack]":
                    # ... [Keeping your existing hijack syntax scanning loop] ...
                    pass

                case _:
                    if curr[0] == '\'':
                        try:
                            c = curr[1:-1]
                            val = ord(c)
                            self.inst("mov", f"rax, {val}")
                            self.push("rax")
                        except:
                            print(f"Compilation Error: Invalid char literal: {curr}")
                            sys.exit(1)
                        self.current_stack_depth += 1

                    elif curr[0] == '"':
                        string_lit = curr
                        if string_lit not in self.string_pool:
                            self.string_pool[string_lit] = len(self.string_pool)
                        str_id = self.string_pool[string_lit]

                        # x86 RIP-relative addressing
                        self.inst("lea", f"rax, [.STR{str_id} + rip]")
                        self.push("rax")
                        self.current_stack_depth += 1

                    elif curr[0] == ".":
                        var = '_' + curr[1:]
                        self.comment("Push variable address")
                        self.inst("lea", f"rax, [{var} + rip]")
                        self.push("rax")
                        self.current_stack_depth += 1

                    elif curr[-1] == '!':
                        proc_callee = curr[:-1]
                        self.comment(f"FFI Call to {proc_callee}")
                        
                        try:
                            params = self.procedure_params[proc_callee]
                        except KeyError:
                            print(f"Compilation Error: Undefined procedure: {proc_callee}")
                            sys.exit(1)

                        # --- Calling Convention mapping for x86_64 System V / Windows ABI ---
                        # Note: You will need to map your popped stack items into structural registers 
                        # (like rdi, rsi, rdx, rcx, r8, r9 for SysV Linux/macOS) based on parameter index `i`
                        
                        self.reserve(32)
                        self.inst("call", f"\"{proc_callee}\"")
                        self.resign(32)

                        type = self.procedure_return[proc_callee]
                        if type != 0:
                            self.push("rax")
                            self.current_stack_depth += 1

                    elif curr[0] == '$':
                        count = curr[1:]
                        if not count.isdigit():
                            print(f"Compilation Error: {curr} is not a valid count")
                            sys.exit(1)
                        self.callee_arg_count = int(count)

                    else:
                        if curr.isdigit():
                            self.inst("mov", f"rax, {curr}")
                            self.push("rax")
                        else:
                            print(f"Compilation Error: Unknown token '{curr}'")
                            sys.exit(1)
                        self.current_stack_depth += 1

            self.advance()

    def gen(self) -> str:
        prev = ""
        curr = self.current()
        
        # self.tag(".file \"{}\"")
        self.tag(".intel_syntax noprefix")
        self.tag(".text")
        
        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            match curr:
                case "static":
                    name = self.next()
                    if name:
                        name = f"{name}"
                        if name in self.statics:
                            print(f"Compilation Error: Static variable {name} already defined")
                            sys.exit(1)
                        
                        self.advance()

                        self.statics[name] = self.current()

                        self.advance()

                        if is_integer(self.current()):
                            self.bss_section.append(f".lcomm {name},{int(self.current()) * Generator.size_of(self.statics[name])},32")
                        else:
                            width = " " * len(name)
                            print(f"Compilation Error: Unexpected token in static variable defintion: '{self.current()}'\n\n\tstatic {name}\n\t~      {width} ^\n\nExpected number of elements")
                            sys.exit(1)
                    
                    else:
                        print("Error: Missing static variable name:\n\tstatic\n\t~      ^")
                        sys.exit(1)
                
                case "extern":
                    proc = self.next()
                    if proc != "proc":
                        print(f"Compilation Error: Expected 'proc' after keyword 'extern' got '{proc}'")
                        sys.exit(1)

                    name = self.next()
                    if name:
                        name = f"{name}"
                        
                        if name in self.procedures:
                            print(f"Compilation Error: extern proc or proc {name} already defined as {self.procedure_params[name]}")
                            sys.exit(1)
                    
                        self.procedures.append(name)

                    
                        curr = self.next()
                        if curr != "(":
                            print(f"Compilation Error: extern proc definition expects parameter list")
                            sys.exit(1)

                        curr = self.next()

                        params: list = []

                        while curr != ")":
                            params.append(curr)
                            curr = self.next()

                        if len(params) > 7:
                            print("Maximum number of procedure arguments reached!\n\tProcedures can only take 7 arguments in Plum v1.0")
                            sys.exit(1)

                        self.procedure_params[name] = params

                        curr = self.next()

                        if curr == ';':
                            self.procedure_return[name] = 0
                        else:
                            self.procedure_return[name] = curr
                            curr = self.next()
                            if curr != ';':
                                print(f"Compilation Error: Expected ';' at end of extern proc definition")
                                sys.exit(1)

                case "proc":
                    name = self.next()
                    if name:
                        if name in self.procedures:
                            print(f"Compilation Error: extern proc or proc {name} already defined")
                            sys.exit(1)
                        
                        self.procedures.append(name)
                        self.current_procedure = name

                        self.tag(f".globl  \"{name}\"")
                        self.tag(f".def    \"{name}\"")
                        self.symbol(name)
                        self.inst("push", "rbp")          # Push SP
                        self.inst("mov", "rbp, rsp")     # Save SP to rsp
                        
                        self.inst("sub", f"rsp, {self.stack_allocation}")

                        curr = self.next()

                        if curr != "(":
                            print(f"Compilation Error: proc definition expects parameter list")
                            sys.exit(1)

                        curr = self.next()

                        params: list = []

                        while curr != ")":
                            params.append(curr)
                            curr = self.next()
                        
                        self.advance()

                        if len(params) > 7:
                            print("Maximum number of procedure arguments reached!\n\tProcedures can only take 7 arguments in Plum v1.0")
                            sys.exit(1)

                        self.procedure_params[name] = params

                        if self.current() == ":":
                            self.procedure_return[name] = 0

                            for i in range(0, len(params)):
                                match params[i]:
                                    case "byte":    self.push_arg(i)
                                    case "word":    self.push_arg(i)
                                    case "dword":   self.push_arg(i)
                                    case "qword":   self.push_arg(i)
                                    case "ptr":     self.push_arg(i)
                                    case "float":   # self.push((i, 1));
                                        print("FLOAT PARAMS NOT IMPLEMENTED YET")
                                    case "double":  # self.push((i, 1));
                                        print("DOUBLE PARAMS NOT IMPLEMENTED YET")
                                    case "[byte4]": 
                                        print("Unpacking of aggregate type [byte4] not implemented yet")
                                        sys.exit(1)
                                    case _:
                                        print(f"Unknown parameter type: {params[i]}")
                                        sys.exit(1)
                        
                            self.current_stack_depth = len(params)

                        elif self.current() == "[hijack]":
                            curr = self.next()

                            if curr == ":":
                                self.procedure_return[name] = 0
                            else:
                                self.procedure_return[name] = curr

                                curr = self.next()

                                if curr != ":":
                                    print(f"Compilation Error: Expected ':' at end of proc header definition, got: {curr}")
                                    sys.exit(1)
                        else:
                            self.procedure_return[name] = curr

                            curr = self.next()
                            
                            if curr != ":":
                                print(f"Compilation Error: Expected ':' at end of proc header definition, got: {curr}")
                                sys.exit(1)
                        
                            for i in range(0, len(params)):
                                match params[i]:
                                    case "byte":    self.push_arg(i)
                                    case "word":    self.push_arg(i)
                                    case "dword":   self.push_arg(i)
                                    case "qword":   self.push_arg(i)
                                    case "ptr":     self.push_arg(i)
                                    case "float":   # self.push((i, 1));
                                        print("FLOAT PARAMS NOT IMPLEMENTED YET")
                                    case "double":  # self.push((i, 1));
                                        print("DOUBLE PARAMS NOT IMPLEMENTED YET")
                                    case "[byte4]": 
                                        print("Unpacking of aggregate type [byte4] not implemented yet")
                                        sys.exit(1)
                                    case _:
                                        print(f"Unknown parameter type: {params[i]}")
                                        sys.exit(1)
                        
                            self.current_stack_depth = len(params)
                        
                        self.advance()

                        self.gen_asm()

                        self.program += self.procedure
                        self.program += "\n"
                        self.procedure = ""
                    else:
                        print("Error: Missing procedure name:\n\tproc\n\t~    ^")
                        sys.exit(1)
                case _:
                    print(f"Error: Unexpected token in program root: {curr}")
                    self.advance()
                    continue

            self.advance()

        bss  = self.gen_BSS()
        strs = self.gen_str_section()
        data = bss + strs

        self.program = data + self.program
        self.program += "#   .ident	\"Built with plum.py, powered by GCC/Clang\"\n"

        return self.program

    def gen_str_section(self) -> str:
        section =  ""
        section += "    .section .rdata,\"dr\"\n"

        for string, str_id in self.string_pool.items():
            section += f".STR{str_id}:\n"
            section += f"    .ascii  {string}\n"
        
        section += "\n"
        return section

    def gen_BSS(self) -> str:
        print("Todo: .file <file>")
        section =  ""
        section += "    # file <filename>"
        section += "    .text\n"
        for bss in self.bss_section:
            section += f"{bss}\n"   
        
        return section
