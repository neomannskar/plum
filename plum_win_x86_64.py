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
        # print(index)
        try:
            return self.ARG_REGS[index][size]
        except:
            return None

    def push_reg(self, index: int) -> str:
        return self.ARG_REGS[index][8]

class Generator:
    source_file: str = ""           # Source code file name
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
    procedure_base_depth: int = 0   # Base de

    procedure: str = ""             # Current procedure code
    
    if_counter: int = 0             # If counter for labels
    while_counter: int = 0          # While counter for labels
    control_stack: list = []        # Control stack for branches
    
    string_pool: dict = {}          # Holds all string literals

    bss_section: list = []          # BSS Data section
    statics: dict = {}              # Static variables [name] = type

    abi: Win64ABI                   # Holds Windows 64 ABI-specific details

    program: str = ""               # Holds compiled program when done

    def __init__(self, source_name: str, tokens: list, str_literals: list):
        self.source_file = source_name
        self.tok_len = len(tokens)
        self.tokens = tokens
        self.str_lits = str_literals
        self.abi = Win64ABI()

    def define_facilities(self):
        self.procedures.append("malloc")
        self.procedure_params["malloc"] = ["dword"]
        self.procedure_return["malloc"] = "ptr"

        self.procedures.append("free")
        self.procedure_params["free"] = ["ptr"]
        self.procedure_return["free"] = 0

        self.procedures.append("exit")
        self.procedure_params["exit"] = ["dword"]
        self.procedure_return["exit"] = 0

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
        self.program += f"{symbol}:\n"
    
    def inst(self, op, operand):
        width = 8
        self.procedure += f"    {op:<{width}}{operand}\n"
    
    def hijack(self, code):
        self.procedure += f"    {code}\n"

    def if_branch(self):
        self.procedure += f".IF_BRANCH_{self.if_counter}:\n"
        self.control_stack.append(("I", self.if_counter, self.current_stack_depth))
        self.if_counter += 1

    def else_branch(self):
        if not self.control_stack or self.control_stack[-1][0] != 'I':
            print(f"Compilation Error: Unexpected 'else', missing associated 'if'")
            sys.exit(1)
        
        block_type, block_id, saved_depth = self.control_stack[-1]

        if self.current_stack_depth > saved_depth:
            self.comment("Else: Auto-dropping")
            self.inst("add", f"rsp, {(self.current_stack_depth - saved_depth) * 8}")
        
        self.current_stack_depth = saved_depth
        
        # Ändrat 'b' till 'jmp' för x86_64
        self.inst("jmp", f".END_BRANCH_{block_id}")
        self.procedure += f".ELSE_BRANCH_{block_id}:\n"
        self.comment("Else-branch:")

    def while_branch(self):
        self.procedure += f".WHILE_START_{self.while_counter}:\n"
        self.control_stack.append(("W", self.while_counter, self.current_stack_depth))
        self.while_counter += 1

    def do(self):
        block_type, block_id, saved_depth = self.control_stack.pop()

        match block_type:
            case 'I':
                # Ändrat x0 -> rax, cmp-syntax och b.eq -> je
                self.pop("rax")
                self.inst("cmp", "rax, 0")
                self.inst("je", f".ELSE_BRANCH_{block_id}")
                self.comment("Then-branch:")
            case 'W':
                # Ändrat x0 -> rax, cmp-syntax och b.eq -> je
                self.pop("rax")
                self.inst("cmp", "rax, 0")
                self.inst("je", f".WHILE_END_{block_id}")
            case _:
                print(f"Implementation Error: Unknown value in control_stack")
                sys.exit(1)
        
        self.current_stack_depth -= 1
        self.control_stack.append((block_type, block_id, self.current_stack_depth))

    def end(self):
        block_type, block_id, saved_depth = self.control_stack.pop()

        if self.current_stack_depth > saved_depth:
            self.comment("End: Auto-dropping")
            self.inst("add", f"rsp, {(self.current_stack_depth - saved_depth) * 8}")
            self.current_stack_depth = saved_depth
        
        match block_type:
            case 'I':
                self.procedure += f".END_BRANCH_{block_id}:\n"
            case 'W':
                # Ändrat 'b' till 'jmp' för x86_64
                self.inst("jmp", f".WHILE_START_{block_id}")
                self.procedure += f".WHILE_END_{block_id}:\n"
            case _:
                print(f"Implementation Error: Unknown value in control_stack")
                sys.exit(1)

    def reserve(self, bytes: int):
        self.inst("sub", f"rsp, {bytes}")
    
    def resign(self, bytes: int):
        self.inst("add", f"rsp, {bytes}")

    def peek(self, reg: str):
        self.inst("mov", f"{reg}, [rsp]")

    def pop(self, reg: str):
        self.inst("pop", f"{reg}")

    def push(self, reg: str):
        self.inst("push", f"{reg}")
    
    def push_arg(self, index: int):
        reg = self.abi.push_reg(index)
        self.inst("push", f"{reg}")
    
    def pop_arg(self, reg: str, size: int):
        self.pop("rax")

        match size:
            case 1:
                self.inst("mov", f"{reg}, al")
            case 2:
                self.inst("mov", f"{reg}, ax")
            case 4:
                self.inst("mov", f"{reg}, eax")
            case 8:
                self.inst("mov", f"{reg}, rax")
            case _:
                print(f"Compilation Error: Unsupported argument size: {size}")
                sys.exit(1)
    
    def home_arg(self, index: int, reg: str):
        if index < 4:
            return
        
        stack_index = index - 4
        offset =  32 + stack_index * 8
        
        self.inst("mov", f"[rsp + {offset}], {reg}")

    def expect_stack(self, count: int):
        if self.current_stack_depth < count:
            print(f"Compilation Error: In procedure {self.current_procedure} -> '{self.current()}' expects at least {count} elements on the stack, got: {self.current_stack_depth}")
            sys.exit(1)
        else:
            pass
            # print(f"In '{self.current_procedure}' -> Current Stack Depth: {self.current_stack_depth}")

    def calc_align(self, depth: int):
        used = depth * 8 + 32
        misalignment = used % 16
        if misalignment == 0:
            return 0
        else:
            return 16 - misalignment

    def get_scratch_reg(self, stack_idx: int, size: int) -> str:
        """Returns a temporary caller-saved scratch register based on size and stack offset."""
        regs = {
            1: ["r10b", "r11b", "al"],
            2: ["r10w", "r11w", "ax"],
            4: ["r10d", "r11d", "eax"],
            8: ["r10", "r11", "rax"]
        }
        pool = regs.get(size, regs[8])
        return pool[stack_idx % len(pool)]

    def call(self, proc: str):
        try:
            params = self.procedure_params[proc]
        except KeyError:
            print(f"Compilation Error: Undefined procedure: {proc}")
            sys.exit(1)

        is_variadic = "..." in params

        args = []
        stack_args = []

        for i, param in enumerate(params):
            match param:
                case "...":
                    break

                case "[byte4]":
                    if hasattr(self, "expect_stack"):
                        self.expect_stack(4)

                    reg = self.abi.argument_reg(i, 4)
                    target_reg = reg if reg else self.get_scratch_reg(len(stack_args), 4)

                    self.pop("rax")               # Pop 'a'
                    self.inst("shl", "eax, 24")   # a << 24

                    self.pop("r10")               # Pop 'b'
                    self.inst("shl", "r10d, 16")  # b << 16
                    self.inst("or", "eax, r10d")

                    self.pop("r11")               # Pop 'g'
                    self.inst("shl", "r11d, 8")   # g << 8
                    self.inst("or", "eax, r11d")

                    self.pop("r10")               # Pop 'r'
                    self.inst("or", "eax, r10d")  # r

                    if target_reg != "eax":
                        self.inst("mov", f"{target_reg}, eax")

                    self.current_stack_depth -= 3

                    if reg is None:
                        stack_args.append((i, target_reg))
                    else:
                        args.append(reg)

                case "byte" | "word" | "dword" | "qword" | "ptr":
                    size_map = {"byte": 1, "word": 2, "dword": 4, "qword": 8, "ptr": 8}
                    size = size_map[param]
                    reg = self.abi.argument_reg(i, size)

                    if reg is None:
                        target_reg = self.get_scratch_reg(len(stack_args), size)
                        self.pop_arg(target_reg, size)
                        stack_args.append((i, target_reg))
                    else:
                        self.pop_arg(reg, size)
                        args.append(reg)

                case "float" | "double":
                    print("Compilation Error: Floating point arguments are not implemented yet!")
                    sys.exit(1)

                case _:
                    print(f"Compilation Error: Unknown parameter type: {param}")
                    sys.exit(1)

            self.current_stack_depth -= 1

        if is_variadic:
            if self.callee_arg_count <= -1:
                print(f"Compilation Error: variadic variable count not set with '$' operator before call to {proc}")
                sys.exit(1)

            for _ in range(self.callee_arg_count):
                idx = len(args) + len(stack_args)
                reg = self.abi.argument_reg(idx, 8)
                if reg is None:
                    target_reg = self.get_scratch_reg(len(stack_args), 8)
                    self.pop_arg(target_reg, 8)
                    stack_args.append((idx, target_reg))
                else:
                    self.pop_arg(reg, 8)
                    args.append(reg)
                self.current_stack_depth -= 1

        alignment = self.calc_align(self.current_stack_depth) + 32

        # Allocate stack frame (including shadow space and stack arguments)
        self.inst("sub", f"rsp, {alignment}")

        if is_variadic:
            for i, reg in enumerate(args):
                self.home_arg(i, reg)
            for i, reg in stack_args:
                self.home_arg(i, reg)
            self.callee_arg_count = -1
        else:
            # Home 5th+ parameters into stack slots ([rsp + 32], [rsp + 40], etc.)
            for i, reg in stack_args:
                self.home_arg(i, reg)

        self.inst("call", f"{proc}")
        self.inst("add", f"rsp, {alignment}")

        type = self.procedure_return[proc]
        if type != 0:
            if type in ["float", "double"]:
                print("Compilation Error: Floating point numbers are not implemented yet!")
                sys.exit(1)
            else:
                self.push("rax")
            self.current_stack_depth += 1

    def gen_asm(self):
        prev = ""
        curr = self.current()

        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            self.comment(curr)
            
            match curr:
                case "intrinsic__printf":
                    print(f"Deprecated: {curr}")
                    sys.exit(1)
                    
                case "intrinsic__printf_ln":
                    print(f"Deprecated: {curr}")
                    sys.exit(1)
                    
                case "intrinsic__scanf":
                    print(f"Deprecated: {curr}")
                    sys.exit(1)
                    
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
                    self.inst("mov", "rdx, [rsp + rax*8]")
                    self.push("rdx")

                case "alloc":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("shl", "rax, 3") # Change this later to either accept types or just do raw bytes
                    self.push("rax")
                    self.call("malloc")

                case "free":
                    self.expect_stack(1)
                    self.call("free")
                    
                case "exit":
                    self.expect_stack(1)
                    self.call("exit")

                case ".":
                    self.expect_stack(1)
                    self.pop("rax")
                    self.inst("mov", "rax, [rax]") # Dereference
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
                    self.inst("mov", "[rdx + rcx*8], rax")
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
                    type = self.procedure_return[self.current_procedure]
                    if (type == "float" or type == "double"):
                        print("Returning floats is not implemented yet!")
                        sys.exit(1)
                    else:
                        self.pop("rax")      # Return value goes into rax
                        self.inst("mov", "rsp, rbp") # Tear down stack frame
                        self.inst("pop", "rbp")
                        self.inst("ret", "")

                case "end":
                    if len(self.control_stack) > 0:
                        self.end()
                    else:
                        type = self.procedure_return[self.current_procedure]
                        if type == 0 and prev != "return":
                            self.inst("mov", "rax, 0")
                            self.inst("mov", "rsp, rbp")
                            self.inst("pop", "rbp")
                            self.inst("ret", "")

                        self.current_stack_depth = 0
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
                    curr = self.next()
                    if curr == "{":
                        curr = self.current()
                        while curr != "}":
                            if len(curr) > 2:
                                self.hijack(curr[1:-1]);
                            curr = self.next()

                        curr = self.next()
                        if curr != ";":
                            self.current_stack_depth += 1
                            continue

                    elif curr[0] == '"':
                        if len(curr) > 2:
                            self.hijack(curr[1:-1]);

                        curr = self.next()
                        if curr != ";":
                            self.current_stack_depth += 1
                            continue
                    else:
                        print("Compilation Error: Expected String literal or block '{ ... }' after in compiler hijack")
                        sys.exit(1)
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
                        self.inst("lea", f"rax, [rip + .STR{str_id}]")
                        self.push("rax")
                        self.current_stack_depth += 1

                    elif curr[0] == ".":
                        var = curr[1:]
                        self.comment("Push variable address")
                        self.inst("lea", f"rax, [{var} + rip]")
                        self.push("rax")
                        self.current_stack_depth += 1

                    elif curr[-1] == '!':
                        proc_callee = curr[:-1]
                        self.comment(f"Load arguments for {proc_callee}")

                        self.call(proc_callee)

                    elif curr[0] == '$':
                        count = curr[1:]
                        if not count.isdigit():
                            print(f"Compilation Error: {curr} is not a valid count")
                            sys.exit(1)
                        self.callee_arg_count = int(count)

                    else:
                        if curr.isdigit():
                            self.push(f"{curr}")
                        else:
                            print(f"Compilation Error: Unknown token '{curr}'")
                            sys.exit(1)
                        self.current_stack_depth += 1

            self.advance()

    def gen(self) -> str:
        prev = ""
        curr = self.current()
        
        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            self.define_facilities()

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

                        self.tag(f".text")
                        self.tag(f".globl  {name}")
                        self.tag(f".def    {name}; .scl 2; .type 32; .endef")
                        self.symbol(name)
                        self.inst("push", "rbp")          # Push SP
                        self.inst("mov", "rbp, rsp")     # Save SP to rsp

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
                            self.procedure_base_depth = self.current_stack_depth

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

        meta = f"	.file	\"{self.source_file}\"\n    .intel_syntax noprefix\n\n"

        bss  = self.gen_BSS()
        strs = self.gen_str_section()
        data = meta + bss + strs

        self.program = data + self.program
        self.program += "#   .ident	\"Built with plum.py, powered by GCC/Clang\"\n"

        return self.program

    def gen_str_section(self) -> str:
        section =  ""
        for string, str_id in self.string_pool.items():
            section += f".STR{str_id}:\n"
            section += f"    .asciz  {string}\n"
        
        if section != "":
            section = "    .section .rdata,\"dr\"\n" + section
        return section

    def gen_BSS(self) -> str:
        section =  ""
        for bss in self.bss_section:
            section += f"{bss}\n"   
        
        if section != "":
            section = "    .text\n" + section
        
        return section
