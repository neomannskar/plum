import sys

def todo():
    print("Not implemented yet!")
    sys.exit(1)

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

    procedure: str = ""             # Current procedure code
    
    if_counter: int = 0             # If counter for labels
    while_counter: int = 0          # While counter for labels
    control_stack: list = []        # Control stack for branches
    
    string_pool: dict = {}          # Holds all string literals

    bss_section: list = []          # BSS Data section
    statics: dict = {}              # Static variables [name] = type

    program: str = ""               # Holds compiled program when done

    def __init__(self, source_name: str, tokens: list, str_literals: list):
        self.source_file = source_name
        self.tok_len = len(tokens)
        self.tokens = tokens
        self.str_lits = str_literals

    def size_of(type) -> int:
        match type:
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
        self.program += ";    {comment}\n"

    def comment(self, comment: str):
        self.procedure += f"    ;    {comment}\n"

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
            self.inst("add", f"sp, sp, #{(self.current_stack_depth - saved_depth) * 16}")
        
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
            self.inst("add", f"sp, sp, #{(self.current_stack_depth - saved_depth) * 16}")
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

    def peek(self, reg: str):
        self.inst("ldr", f"{reg}, [sp]")

    def pop(self, reg: str):
        self.inst("ldr", f"{reg}, [sp], #16")

    def push(self, reg: str):
        self.inst("str", f"{reg}, [sp, #-16]!")
    
    def expect_stack(self, count: int):
        if self.current_stack_depth < count:
            print(f"Compilation Error: '{self.current()}' expects at least {count} elements on the stack, got: {self.current_stack_depth}")
            sys.exit(1)

    def call(self, proc: str):
        try:
            params = self.procedure_params[proc]
        except KeyError:
            print(f"Compilation Error: Undefined procedure: {proc}")
            sys.exit(1)
        
        i = 0
        is_variadic = False
        if "..." in params:
            is_variadic = True
            if self.callee_arg_count > -1:
                self.expect_stack(self.callee_arg_count)
                self.current_stack_depth -= (self.callee_arg_count)
            else:
                print("Compilation Error: variadic variable count not set with '$' operator before call to variadic procedure")
                sys.exit(1)

        for param in params:
            if param == "...":
                if len(params) < 2 and params[-1] != "...":
                    print("Compilation Error: Variadics must be at end of parameter list and can't be the only parameter!")
                    sys.exit(1)
                break
            else:
                match param:
                    case "byte":    # 8-bit
                        self.expect_stack(1)
                        self.inst("ldr", f"w{i}, [sp], #16")
                    case "word":    # 16-bit
                        self.expect_stack(1)
                        self.inst("ldr", f"w{i}, [sp], #16")
                    case "dword":   # 32-bit
                        self.expect_stack(1)
                        self.pop(f"w{i}")
                    case "qword":   # 64-bit
                        self.expect_stack(1)
                        self.pop(f"x{i}")
                    case "ptr":     # 64-bit
                        self.expect_stack(1)
                        self.pop(f"x{i}")
                    case "float":   # 32-bit
                        self.expect_stack(1)
                        self.inst("ldr", f"s{i}, [sp], #16")
                    case "double":  # 64-bit
                        self.expect_stack(1)
                        self.inst("ldr", f"v{i}, [sp], #16")
                    case "[byte4]":
                        self.expect_stack(4)

                        self.pop("x9")   # a
                        self.pop("x10")  # b
                        self.pop("x11")  # g
                        self.pop("x12")  # r

                        # Pack into x12
                        self.inst("lsl", "x11, x11, #8")     # g << 8
                        self.inst("lsl", "x10, x10, #16")    # b << 16
                        self.inst("lsl", "x9, x9, #24")      # a << 24

                        self.inst("orr", "x12, x12, x11")
                        self.inst("orr", "x12, x12, x10")
                        self.inst("orr", "x12, x12, x9")

                        self.inst("mov", f"w{i}, w12")

                        self.current_stack_depth -= 3
                    case _:
                        print(f"Unknown parameter type: {param}")
                        sys.exit(1)

                i += 1

                self.current_stack_depth -= 1
        
        if is_variadic and self.callee_arg_count > -1:
            N = self.callee_arg_count
            aligned_size = ((N + 1) // 2) * 16
            
            if aligned_size > 0:
                self.comment("Repack variadic arguments for macOS ABI (8-byte slots)")
                self.inst("sub", f"sp, sp, #{aligned_size}")
            
            for j in range(N):
                old_offset = aligned_size + (j * 16)
                new_offset = j * 8
                
                self.inst("ldr", f"x9, [sp, #{old_offset}]")
                self.inst("str", f"x9, [sp, #{new_offset}]")

        if not proc in self.procedures:
            print(f"Compilation Error: No known procedure: {proc}")
            sys.exit(1)
        
        self.comment("Call")
        self.inst("bl", f"{proc}")
        if is_variadic:
            if self.callee_arg_count > -1:
                aligned_size = ((self.callee_arg_count + 1) // 2) * 16
                total_cleanup = aligned_size + (self.callee_arg_count * 16)
                
                self.inst("add", f"sp, sp, #{total_cleanup}")
                self.callee_arg_count = -1
            else:
                print(f"Compilation Error: variadic variable count not set with '$' operator before call to variadic procedure: {self.callee_arg_count}")
                sys.exit(1)
        
        type = self.procedure_return[proc]
        if type == 0:
            pass
        elif type == "float" or type == "double":
            self.push("v0")
            self.current_stack_depth += 1
        else:
            self.push("x0")
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
                    # special case
                    self.pop("x0")
                    self.inst("bl", "_printf")
                    self.inst("add", "sp, sp, #16")

                    self.current_stack_depth -= 2
                case "intrinsic__printf_ln":
                    # special case
                    self.pop("x0")
                    self.inst("bl", "_printf")
                    self.inst("add", "sp, sp, #16")
                    self.inst("mov", "x0, #10")
                    self.inst("bl", "_putchar")

                    self.current_stack_depth -= 2
                case "intrinsic__scanf":
                    # special case
                    self.pop("x0")
                    self.inst("bl", "_scanf")
                    self.inst("add", "sp, sp, #16")

                    self.current_stack_depth -= 2
                case "dup":
                    self.expect_stack(1)

                    self.peek("x0")
                    self.push("x0")

                    self.current_stack_depth += 1
                    
                case "drop":
                    self.expect_stack(1)

                    self.inst("add", "sp, sp, #16")

                    self.current_stack_depth -= 1
                case "swap":
                    self.expect_stack(2)

                    self.peek("x0")
                    self.inst("ldr", "x1, [sp, #16]")
                    self.inst("str", "x1, [sp]")
                    self.inst("str", "x0, [sp, #16]")
                case "rot":
                    self.expect_stack(3)
                    self.comment("[a, b, c] --> [b, c, a]")
                    self.peek("x0")
                    self.inst("ldr", "x1, [sp, #16]")
                    self.inst("ldr", "x2, [sp, #32]")
                    self.inst("str", "x1, [sp, #32]")
                    self.inst("str", "x0, [sp, #16]")
                    self.inst("str", "x2, [sp]")

                case "over":
                    self.expect_stack(2)

                    self.inst("ldr", "x0, [sp, #16]")
                    self.push("x0")

                    self.current_stack_depth += 1
                case "pick":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("lsl", "x1, x0, #4")
                    self.inst("ldr", "x2, [sp, x1]")
                    self.push("x2")

                case "alloc":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("lsl", "x0, x0, #3")
                    self.inst("bl", "_malloc")
                    self.push("x0")

                case "free":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("bl", "_free")
                    
                    self.current_stack_depth -= 1
                case "exit":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("bl", "_exit")

                    self.current_stack_depth -= 1
                case ".":
                    self.expect_stack(1)

                    self.inst("mov", "x0, #0")
                    self.pop("x1")
                    self.inst("ldr", "x0, [x1, x0, lsl #3]")
                    self.push("x0")

                case "[]":
                    self.expect_stack(2)

                    self.pop("x0")
                    self.pop("x1")
                    self.inst("ldr", "x0, [x1, x0, lsl #3]")
                    self.push("x0")

                    self.current_stack_depth -= 1
                case "=":
                    self.expect_stack(2)

                    self.pop("x0")
                    self.inst("mov", "x1, #0")
                    self.pop("x2")
                    self.inst("str", "x0, [x2, x1, lsl #3]")

                    self.current_stack_depth -= 2
                case "[]=":
                    self.expect_stack(3)

                    self.pop("x0")
                    self.pop("x1")
                    self.pop("x2")
                    self.inst("str", "x0, [x2, x1, lsl #3]")

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
                        self.pop("v0")
                        self.inst("ldp", "x29, x30, [sp], #16")
                        self.inst("ret", "")
                    else:
                        self.pop("x0")
                        self.inst("ldp", "x29, x30, [sp], #16")
                        self.inst("ret", "")

                case "end":
                    if len(self.control_stack) > 0:
                        self.end()
                    else:
                        type = self.procedure_return[self.current_procedure]
                        if type == 0 and prev != "return":
                            self.inst("mov", "x0, #0")
                            self.inst("ldp", "x29, x30, [sp], #16")
                            self.inst("ret", "")
                        
                        self.current_stack_depth = 0
                        return
                case "++":
                    self.pop("x0")
                    self.inst("add", "x0, x0, #1")
                    self.push("x0")
                case "--":
                    self.pop("x0")
                    self.inst("sub", "x0, x0, #1")
                    self.push("x0")
                case "+":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("add", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "-":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sub", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "*":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("mul", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "/":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sdiv", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case '%':
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sdiv", "x2, x0, x1")
                    self.inst("msub", "x0, x2, x1, x0")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "&":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("and", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "|":
                    self.expect_stack(2)
                    
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("orr", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "^":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("eor", "x0, x0, x1")
                    self.push("x0")

                    self.current_stack_depth -= 1
                case "~":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("mvn", "x0, x0")
                    self.push("x0")
                case "neg":
                    self.expect_stack(1)

                    self.pop("x0")
                    self.inst("neg", "x0, x0")
                    self.push("x0")
                case "<<":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("lsl", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case ">>":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("asr", "x0, x0, x1")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "<":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, lt")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case ">":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, gt")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "==":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, eq")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "!=":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, ne")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case "<=":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, le")
                    self.push("x0")
                    
                    self.current_stack_depth -= 1
                case ">=":
                    self.expect_stack(2)

                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, ge")
                    self.push("x0")
                    
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
                            self.inst("mov", f"x0, #{val}")
                            self.push("x0")
                        except:
                            print(f"Compilation Error: Char literal is not a char literal: {curr}")
                            sys.exit(1)

                        self.current_stack_depth += 1
                    elif curr[0] == '"':
                        string_lit = curr
                        if string_lit not in self.string_pool:
                            self.string_pool[string_lit] = len(self.string_pool)
                        str_id = self.string_pool[string_lit]

                        self.inst("adrp", f"x0, l_.STR.{str_id}@PAGE")
                        self.inst("add", f"x0, x0, l_.STR.{str_id}@PAGEOFF")
                        self.push("x0")

                        self.current_stack_depth += 1
                    elif curr[0] == ".":
                        var = '_' + curr[1:]
                        self.comment("Push variable address")
                        self.inst("adrp", f"x0, {var}@PAGE")
                        self.inst("add", f"x0, x0, {var}@PAGEOFF")
                        self.push("x0")

                        self.current_stack_depth += 1
                    elif curr[-1] == '!':
                        proc_callee = '_' + curr[:-1]
                        self.comment(f"Load arguments for {proc_callee}")
                        
                        self.call(proc_callee)
                        
                    elif curr[0] == '$':
                        count = curr[1:]
                        if not is_integer(count):
                            print(f"Compilation Error: {curr} is not a valid variadic argument count")
                            sys.exit(1)
                        else:
                            self.callee_arg_count = int(count)
                    else:
                        if is_integer(curr):
                            self.inst("mov", f"x0, #{curr}")
                            self.push("x0")
                        elif is_float(curr):
                            self.inst("movf", f"v0, #{curr}")
                            self.push("v0")
                        else:
                            print(f"Compilation Error: Token '{curr}' is not an integer or a float value")
                            sys.exit(1)
                        
                        self.current_stack_depth += 1

            self.advance()

    def gen(self) -> str:
        prev = ""
        curr = self.current()
        
        self.tag(f".file  \"{self.source_file}\"")
        self.tag(".section	__TEXT,__text,regular,pure_instructions")
        self.tag(".build_version macos, 26, 0	sdk_version 26, 2")
        
        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            match curr:
                case "static":
                    name = self.next()
                    if name:
                        name = f"_{name}"
                        if name in self.statics:
                            print(f"Compilation Error: Static variable {name[1:]} already defined")
                            sys.exit(1)
                        
                        self.advance()

                        self.statics[name] = self.current()

                        self.advance()

                        if is_integer(self.current()):
                            self.bss_section.append(f".zerofill __DATA,__bss,{name},{int(self.current()) * Generator.size_of(self.statics[name])},3")
                        else:
                            width = " " * len(name[1:])
                            print(f"Compilation Error: Unexpected token in static variable defintion: '{self.current()}'\n\n\tstatic {name[1:]}\n\t~      {width} ^\n\nExpected number of elements")
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
                        name = f"_{name}"
                        
                        if name in self.procedures:
                            print(f"Compilation Error: extern proc or proc {name[1:]} already defined as {self.procedure_params[name]}")
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
                        name = f"_{name}"
                        
                        if name in self.procedures:
                            print(f"Compilation Error: extern proc or proc {name[1:]} already defined")
                            sys.exit(1)
                        
                        print(name, self.current_stack_depth)
                        self.procedures.append(name)
                        self.current_procedure = name

                        self.tag(f".globl  {name}")
                        self.tag(".p2align    2")
                        self.symbol(name)
                        self.inst("stp", "x29, x30, [sp, #-16]!")
                        
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

                            for i in range(0, len(self.procedure_params[name])):
                                self.push(f"x{i}")
                        
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
                        
                            for i in range(0, len(self.procedure_params[name])):
                                self.push(f"x{i}")
                        
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
        
        self.program += "\n"
        self.gen_str_section()
        self.gen_BSS()

        return self.program

    def gen_str_section(self):
        section = ""

        for string, str_id in self.string_pool.items():
            section += f"l_.STR.{str_id}:\n"
            section += f"    .asciz  {string}\n"
        
        section += "\n"
        self.program += section

    def gen_BSS(self):
        for bss in self.bss_section:
            self.program += f"{bss}\n"
