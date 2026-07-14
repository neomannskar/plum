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

class Generator:
    tokens: list
    str_lits: list
    tok_len: int = 0
    tok_iter: int = 0
    procedures: list = []
    procedure_args: dict = {}
    procedure: list = []
    procedure: str = ""
    
    if_counter: int = 0
    while_counter: int = 0
    control_stack: list = []

    string_pool: dict = {}

    bss_section: list = []
    statics: list = []

    program: str = ""

    def __init__(self, tokens, str_literals):
        self.tok_len = len(tokens)
        self.tokens = tokens
        self.str_lits = str_literals
        pass

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

    def if_branch(self):
        self.procedure += f".IF_BRANCH_{self.if_counter}:"
        self.control_stack.append(f"I{self.if_counter}")
        self.if_counter += 1
        #initial_depth = stack_depth
    
    def else_branch(self):
        """
        if stack_depth > initial_depth:
            program += "; Auto-drop\n"
            program += f"    add     sp, sp, #{(stack_depth - initial_depth) * 16}\n"
            stack_depth = initial_depth
        
        if control_stack[-1][0] != 'I':
                print(f"Compilation Error: Unexpected 'else', missing associated 'if'\n\tFound: {control_stack[-1]}")
                sys.exit(1)
        """

        _if = self.control_stack[-1][-1]
        self.inst("b", f".END_BRANCH_{_if}")
        self.procedure += f".ELSE_BRANCH_{_if}:\n"
        self.comment("Else-branch:")
        #stack_depth = initial_depth

    def while_branch(self):
        self.procedure += f".WHILE_START_{self.while_counter}:"
        self.control_stack.append(f"W{self.while_counter}")
        self.while_counter += 1
        #initial_depth = stack_depth
    
    def do(self):
        match self.control_stack[-1][0]:
            case 'I':
                _if = self.control_stack[-1][-1]
                self.pop("x0")
                self.inst("cmp", "x0, #0")
                self.inst("b.eq", f".ELSE_BRANCH_{_if}")
                self.comment("Then-branch:")
            case 'W':
                _while = self.control_stack[-1][-1]
                self.pop("x0")
                self.inst("cmp", "x0, #0")
                self.inst("b.eq", f".WHILE_END_{_while}")
            case _:
                print(f"Implementation Error: Unknown value in control_stack: {self.control_stack[-1]}")
                sys.exit(1)
        #stack_depth -= 1

    def end(self):
        """
        if stack_depth > initial_depth:
            program += "; Auto-drop\n"
            program += f"    add     sp, sp, #{(stack_depth - initial_depth) * 16}\n"
            stack_depth = initial_depth
        """
        id_val = self.control_stack.pop()
        id = id_val[-1]
        match id_val[0]:
            case 'I':
                self.procedure += f".END_BRANCH_{id}:\n"
            case 'W':
                self.inst("b", f".WHILE_START_{id}")
                self.procedure += f".WHILE_END_{id}:\n"
            case _:
                print(f"Implementation Error: Unknown value in control_stack: {self.control_stack[-1]}")
                sys.exit(1)

    def peek(self, reg: str):
        self.inst("ldr", f"{reg}, [sp]")

    def pop(self, reg: str):
        self.inst("ldr", f"{reg}, [sp], #16")

    def push(self, reg: str):
        self.inst("str", f"{reg}, [sp, #-16]!")

    def gen_asm(self):
        prev = ""
        curr = self.current()

        while self.tok_iter < self.tok_len:
            prev = curr
            curr = self.current()

            self.comment(curr)
            
            match curr:
                case "intrinsic__printf":
                    # Handle type_stack
                    self.pop("x0")
                    self.inst("bl", "_printf")
                    self.inst("add", "sp, sp, #16")
                    # stack_depth -= 2
                case "intrinsic__printf_ln":
                    self.pop("x0")
                    self.inst("bl", "_printf")
                    self.inst("add", "sp, sp, #16")
                    self.inst("mov", "x0, #10")
                    self.inst("bl", "_putchar")
                    # stack_depth -= 2
                case "intrinsic__scanf":
                    self.pop("x0")
                    self.inst("bl", "_scanf")
                    self.inst("add", "sp, sp, #16")
                    # stack_depth += 1
                case "dup":
                    self.peek("x0")
                    self.push("x0")
                    # stack_depth += 1
                case "drop":
                    self.inst("add", "sp, sp, #16")
                    # stack_depth -= 1
                case "swap":
                    self.peek("x0")
                    self.inst("ldr", "x1, [sp, #16]")
                    self.inst("str", "x1, [sp]")
                    self.inst("str", "x0, [sp, #16]")
                case "rot":
                    self.comment("[a, b, c] --> [b, c, a]")
                    self.peek("x0")
                    self.inst("ldr", "x1, [sp, #16]")
                    self.inst("ldr", "x2, [sp, #32]")
                    self.inst("str", "x1, [sp, #32]")
                    self.inst("str", "x0, [sp, #16]")
                    self.inst("str", "x2, [sp]")
                case "over":
                    self.inst("ldr", "x0, [sp, #16]")
                    self.push("x0")
                    # stack_depth += 1
                case "pick":
                    self.comment("[a, b, c][1] --> [a, b, c, b]")
                    self.pop("x0")
                    self.inst("lsl", "x1, x0, #4")
                    self.inst("ldr", "x2, [sp, x1]")
                    self.push("x2")
                    # stack_depth += 1
                case "alloc":
                    self.pop("x0")
                    self.inst("lsl", "x0, x0, #3")
                    self.inst("bl", "_malloc")
                    self.push("x0")
                case "free":
                    self.pop("x0")
                    self.inst("bl", "_free")
                    # stack_depth -= 1
                case "exit":
                    self.pop("x0")
                    self.inst("bl", "_exit")
                case "[]":
                    self.pop("x0")
                    self.pop("x1")
                    self.inst("ldr", "x0, [x1, x0, lsl #3]")
                    self.push("x0")
                    # stack_depth -= 1
                case "[]=":
                    self.pop("x0")
                    self.pop("x1")
                    self.pop("x2")
                    self.inst("str", "x0, [x2, x1, lsl #3]")
                    # stack_depth -= 3
                case "if":
                    self.if_branch()
                case "while":
                    self.while_branch()
                case "do":
                    self.do()
                case "else":
                    self.else_branch()
                case "return":
                    self.pop("x0")
                    self.inst("ldp", "x29, x30, [sp], #16")
                    self.inst("ret", "")
                case "end":
                    if len(self.control_stack) > 0:
                        self.end()
                    else:
                        # self.pop("x0")
                        # self.inst("mov", "x0, #0")
                        # self.inst("ldp", "x29, x30, [sp], #16")
                        # self.inst("ret", "")
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
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("add", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "-":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sub", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "*":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("mul", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "/":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sdiv", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case '%':
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("sdiv", "x2, x0, x1")
                    self.inst("msub", "x0, x2, x1, x0")
                    self.push("x0")
                    # stack_depth -= 1
                case "&":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("and", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "|":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("orr", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "^":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("eor", "x0, x0, x1")
                    self.push("x0")
                case "~":
                    self.pop("x0")
                    self.inst("mvn", "x0, x0")
                    self.push("x0")
                case "<<":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("lsl", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case ">>":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("asr", "x0, x0, x1")
                    self.push("x0")
                    # stack_depth -= 1
                case "<":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, lt")
                    self.push("x0")
                    # stack_depth -= 1
                case ">":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, gt")
                    self.push("x0")
                    # stack_depth -= 1
                case "==":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, eq")
                    self.push("x0")
                    # stack_depth -= 1
                case "!=":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, ne")
                    self.push("x0")
                    # stack_depth -= 1
                case "<=":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, le")
                    self.push("x0")
                    # stack_depth -= 1
                case ">=":
                    self.pop("x1")
                    self.pop("x0")
                    self.inst("cmp", "x0, x1")
                    self.inst("cset", "x0, ge")
                    self.push("x0")
                    # stack_depth -= 1
                case _:
                    if curr[0] == '"':
                        string_lit = curr
                        if string_lit not in self.string_pool:
                            self.string_pool[string_lit] = len(self.string_pool)
                        str_id = self.string_pool[string_lit]

                        self.inst("adrp", f"x0, l_.STR.{str_id}@PAGE")
                        self.inst("add", f"x0, x0, l_.STR.{str_id}@PAGEOFF")
                        self.push("x0")
                        # stack_depth += 1
                    elif curr[0] == ".":
                        var = '_' + curr[1:]
                        self.comment("Push variable address")
                        self.inst("adrp", f"x0, {var}@PAGE")
                        self.inst("add", f"x0, x0, {var}@PAGEOFF")
                        self.push("x0")
                        # stack_depth += 1
                    elif curr[-1] == '!':
                        proc_callee = '_' + curr[:-1]
                        self.comment("Load arguments")
                        
                        try:
                            args = self.procedure_args[proc_callee]
                        except KeyError:
                            print(f"Compilation Error: Undefined procedure: {proc_callee[1:]}")
                            sys.exit(1)
                        
                        for i in range(0, args):
                            self.inst("ldr", f"x{i}, [sp], #16") # pop from stack

                        if not proc_callee in self.procedures:
                            print(f"Compilation Error: No known procedure: {proc_callee[1:]}")
                            sys.exit(1)
                        
                        self.comment("Call")
                        self.inst("bl", f"{proc_callee}")
                        
                        # if return_val:
                        self.push("x0")
                    else:
                        if not is_integer(curr):
                            print(f"Compilation Error: Unexpected token: {curr}")
                            sys.exit(1)
                        
                        self.inst("mov", f"x0, #{curr}")
                        self.push("x0")
                        # stack_depth += 1

            self.advance()

    def gen(self) -> str:
        prev = ""
        curr = self.current()
        
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
                        
                        self.statics.append(name)
                        self.advance()

                        if is_integer(self.current()):
                            self.bss_section.append(f".zerofill __DATA,__bss,{name},{int(self.current()) * 8},3")
                        else:
                            width = " " * len(name[1:])
                            print(f"Compilation Error: Unexpected token in static variable defintion: '{self.current()}'\n\n\tstatic {name[1:]}\n\t~      {width} ^\n\nExpected number of elements")
                            sys.exit(1)
                    
                    else:
                        print("Error: Missing static variable name:\n\tstatic\n\t~      ^")
                        sys.exit(1)

                case "proc":
                    name = self.next()
                    if name:
                        name = f"_{name}"
                        
                        if name in self.procedures:
                            print(f"Compilation Error: Procedure {name[1:]} already defined")
                            sys.exit(1)
                        
                        self.procedures.append(name)

                        self.tag(f".globl  {name}")
                        self.tag(".p2align    2")
                        self.symbol(name)
                        self.inst("stp", "x29, x30, [sp, #-16]!")
                        
                        self.advance()
                        if self.current() == ":":
                            self.procedure_args[name] = 0
                        elif is_integer(self.current()):
                            i = int(self.current())
                            if i > 7:
                                print("Maximum number of procedure arguments reached!\n\tProcedures can only take 7 arguments in Plum v1.0")
                                sys.exit(1)
                            
                            self.procedure_args[name] = i
                            self.advance()
                            if self.current() != ":":
                                width = " " * len(name[1:])
                                print(f"Compilation Error: Unexpected token in procedure defintion: '{self.current()}'\n\n\tproc {name[1:]} {i}\n\t~    {width}  ^\n\nExpected number of arguments or an opening ':'")
                                sys.exit(1)
                        else:
                            width = " " * len(name[1:])
                            print(f"Compilation Error: Unexpected token in procedure defintion: '{self.current()}'\n\n\tproc {name[1:]}\n\t~    {width} ^\n\nExpected number of arguments or an opening ':'")
                            sys.exit(1)
                        
                        for i in range(0, self.procedure_args[name]):
                            self.push(f"x{i}")
                        
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
