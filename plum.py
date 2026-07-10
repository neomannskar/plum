import re
import sys
import platform
import subprocess

SIM = False

lines = []

STRING_REGEX = r'"[^"\n]*"'

if len(sys.argv) < 4:
    print("Usage: python plum.py <.plum file> <.s file> <program>")
    sys.exit(1)

s_file = sys.argv[1]
a_file = sys.argv[2]
o_file = sys.argv[3]

with open(s_file) as f:
    source_code = f.read()

tokens = []
str_literals = []
chunks = re.split(f'({STRING_REGEX})', source_code)

for chunk in chunks:
    if not chunk:
        continue
    if chunk.startswith('"') and chunk.endswith('"'):
        tokens.append(chunk)
        str_literals.append(chunk)
    else:
        tokens.extend(chunk.split())

def get_str_id(lit) -> int:
    i = 0
    for string in str_literals:
        if string == lit:
            return i
        else:
            i += 1
            continue
    
    return -1

tok_i = 0

def gen_asm_x86_64(tokens) -> str:
    program = ""
    tok_i = 0
    while_counter = 0
    control_stack = []

    while tok_i < len(tokens):
        tok = tokens[tok_i]

        if tok ==  "print":
            program += "    popq    %rdx\n"
            program += "    movq    %rsp, %rax\n"
            program += "    andq    $-16, %rsp\n"
            program += "    subq    $48, %rsp\n"
            program += "    movq    %rax, 32(%rsp)\n"
            program += "    leaq    .PRINT_NUMBER(%rip), %rax\n"
            program += "    movq    %rax, %rcx\n"
            program += "    call    printf\n"
            program += "    movq    32(%rsp), %rsp\n"
            tok_i += 1

        elif tokens[tok_i] == "dup":
            program += "    popq    %rax\n"
            program += "    pushq   %rax\n"
            program += "    pushq   %rax\n" 
            tok_i += 1

        elif tok == "+":
            program += "    popq    %rax\n"
            program += "    popq    %rbx\n"
            program += "    addq    %rbx, %rax\n"
            program += "    pushq   %rax\n"
            tok_i += 1

        elif tokens[tok_i] == "-":
            program += "    popq    %rbx\n"
            program += "    popq    %rax\n"
            program += "    subq    %rbx, %rax\n"
            program += "    pushq   %rax\n"
            tok_i += 1

        elif tokens[tok_i] == '*':
            program += "    popq    %rbx\n"
            program += "    popq    %rax\n"
            program += "    imulq    %rbx, %rax\n"
            program += "    pushq   %rax\n"
            tok_i += 1

        elif tokens[tok_i] == '/':
            program += "    popq    %rbx\n" # divisor
            program += "    popq    %rax\n" # dividend

            program += "    cqto\n" # sign-extend %rax into %rdx to form the 128-bit dividend %rdx:%rax

            program += "    idivq   %rbx\n"
            program += "    pushq   %rax\n" 
            tok_i += 1

        elif tok == "while":
            program += f".WHILE_START_{while_counter}:\n"
            
            control_stack.append(while_counter)
            while_counter += 1
            tok_i += 1

        elif tok == "<":
            program += "    popq    %rbx\n"
            program += "    popq    %rax\n"
            program += "    cmpq    %rbx, %rax\n"
            
            program += "    setl    %al\n"
            program += "    movzbl  %al, %eax\n"
            program += "    pushq   %rax\n"
            tok_i += 1

        elif tok == "do":
            current_while = control_stack[-1]
            program += "    popq    %rax\n"
            program += "    cmpq    $0, %rax\n"
            program += f"    je .WHILE_END_{current_while}\n"
            tok_i += 1

        elif tok == "end":
            current_while = control_stack.pop()
            program += f"    jmp .WHILE_START_{current_while}\n"
            program += f".WHILE_END_{current_while}:\n"
            program += "    movq    %rbp, %rsp\n" # reset the stack
            tok_i += 1

        elif tok[0] == '"': # String literal
            # push length
            # push pointer
            # tok_i += 1
            pass

        else:
            # It's an integer literal
            program += f"    pushq   ${tok}\n"
            tok_i += 1

    return program

def gen_asm_ARM(tokens) -> str:
    program = ""
    tok_i = 0
    while_counter = 0
    if_counter = 0
    control_stack = []
    type_stack = []
    stack_depth = 0
    initial_depth = stack_depth

    while tok_i < len(tokens):
        tok = tokens[tok_i]

        program += f"    ;    {tok}\n"

        if tok ==  "print": # Print
            t = type_stack.pop()

            if t == "INT":
                # Load format string address into x0 (first argument)
                program += "    adrp    x0, l_.PRINT_NUMBER@PAGE\n"
                program += "    add     x0, x0, l_.PRINT_NUMBER@PAGEOFF\n"
                program += "    bl      _printf\n"
                # Due to Mac ABI
                program += "    add     sp, sp, #16\n"

            elif t == "STR":
                program += "    ldr     x0, [sp], #16\n"
                program += "    bl      _puts\n"

            else:
                print("Internal Error: Unknown strlit in type_stack")
                sys.exit(0)

            stack_depth -= 1
            tok_i += 1
        
        elif tok == "?":
            program += "    adrp    x1, _io@PAGE\n"
            program += "    add     x1, x1, _io@PAGEOFF\n"

            # Push resulting buffer
            program += "    ;    push buffer address\n"
            program += "    str     x1, [sp, #-16]!\n"
            
            program += "    adrp    x0, l_.SCANF_255s_FMT@PAGE\n"
            program += "    add     x0, x0, l_.SCANF_255s_FMT@PAGEOFF\n"
            program += "    bl      _scanf\n"

            type_stack.append("STR")

            stack_depth += 1

            tok_i += 1

        elif tok == "dup": # Duplication
            if len(type_stack) > 0:
                t = type_stack[-1]
                type_stack.append(t)
            else:
                print("Compilation Error: 'dup' expects at least one value on the stack")
                sys.exit(1)

            program += "    ldr     x0, [sp]\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            stack_depth += 1
            tok_i += 1

        elif tok == "drop": # Duplication
            if len(type_stack) > 0:
                t = type_stack[-1]
                type_stack.append(t)
            else:
                print("Compilation Error: 'drop' expects at least one value on the stack")
                sys.exit(1)

            program += "    add     sp, sp, #16\n"
            
            stack_depth += 1
            tok_i += 1

        elif tok == "swap": # Swap top values of stack
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                type_stack.append(t2)
                type_stack.append(t1)
            else:
                print("Compilation Error: 'swap' expects at least two values on the stack")
                sys.exit(1)    

            program += "    ldr    x0, [sp], #16\n"
            program += "    ldr    x1, [sp], #16\n"
            program += "    str    x1, [sp, #-16]!\n"
            program += "    str    x0, [sp, #-16]!\n"

            tok_i += 1

        elif tok == "+": # Addition
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '+' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)
            
            type_stack.append("INT")

            program += "    ldr     x0, [sp], #16\n"  # pop x0
            program += "    ldr     x1, [sp], #16\n"  # pop x1
            program += "    add     x0, x1, x0\n"
            program += "    str     x0, [sp, #-16]!\n" # push result

           
            stack_depth -= 1
            tok_i += 1

        elif tok == "-": # Subtraction
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '-' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)
            
            type_stack.append("INT")

            program += "    ldr     x1, [sp], #16\n"  # pop rbx equivalent (divisor/subtrahend)
            program += "    ldr     x0, [sp], #16\n"  # pop rax equivalent (minuend)
            program += "    sub     x0, x0, x1\n"
            program += "    str     x0, [sp, #-16]!\n"
            
           
            stack_depth -= 1
            tok_i += 1

        elif tok == '*': # Multiplication
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '*' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)

            program += "    ldr     x1, [sp], #16\n"
            program += "    ldr     x0, [sp], #16\n"
            program += "    mul     x0, x0, x1\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            type_stack.append("INT")
            
           
            stack_depth -= 1
            tok_i += 1

        elif tok == '/': # Division
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '/' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # divisor
            program += "    ldr     x0, [sp], #16\n"  # dividend
            program += "    sdiv    x0, x0, x1\n"     # x0 = x0 / x1
            program += "    str     x0, [sp, #-16]!\n"

            type_stack.append("INT")
            
           
            stack_depth -= 1
            tok_i += 1

        elif tok == '%': # Modulo
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '%' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # divisor
            program += "    ldr     x0, [sp], #16\n"  # dividend
            program += "    sdiv    x2, x0, x1\n"     # x2 = x0 / x1
            program += "    msub    x0, x2, x1, x0\n" # x0 = x0 - (x2 * x1)
            program += "    str     x0, [sp, #-16]!\n"

            type_stack.append("INT")
            
            stack_depth -= 1
            tok_i += 1

        elif tok == "<": # Less than
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '<' expects two integers")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # b
            program += "    ldr     x0, [sp], #16\n"  # a
            program += "    cmp     x0, x1\n"
            # cset sets register to 1 if condition (lt = less than) is true, else 0
            program += "    cset    x0, lt\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            type_stack.append("INT")    

           
            stack_depth -= 1
            tok_i += 1

        elif tok == ">": # Greater than
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '>' expects two integers")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # b
            program += "    ldr     x0, [sp], #16\n"  # a
            program += "    cmp     x0, x1\n"
            # cset sets register to 1 if condition (lt = less than) is true, else 0
            program += "    cset    x0, gt\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            type_stack.append("INT")

           
            stack_depth -= 1
            tok_i += 1

        elif tok == "==": # Equal to
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '=' expects two integers")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # b
            program += "    ldr     x0, [sp], #16\n"  # a
            program += "    cmp     x0, x1\n"
            # cset sets register to 1 if condition (eq = equal) is true, else 0
            program += "    cset    x0, eq\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            type_stack.append("INT")

            stack_depth -= 1
            tok_i += 1

        elif tok == "!=": # Not equal
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '!=' expects two integers")
                    sys.exit(1)
            
            program += "    ldr     x1, [sp], #16\n"  # b
            program += "    ldr     x0, [sp], #16\n"  # a
            program += "    cmp     x0, x1\n"
            # cset sets register to 1 if condition (eq = equal) is true, else 0
            program += "    cset    x0, ne\n"
            program += "    str     x0, [sp, #-16]!\n"
            
            type_stack.append("INT")
            
            stack_depth -= 1
            tok_i += 1

        elif tok == "if": # If
            program += f".IF_BRANCH_{if_counter}:\n"
            control_stack.append(f"I{if_counter}")
            if_counter += 1
            initial_depth = stack_depth
            
            tok_i += 1
        
        elif tok == "while": # While
            program += f".WHILE_START_{while_counter}:\n"
            control_stack.append(f"W{while_counter}")
            while_counter += 1
            initial_depth = stack_depth
            tok_i += 1

        elif tok == "do": # Do
            match control_stack[-1][0]:
                case 'I':
                    _if = control_stack[-1][-1]
                    program +=  "    ldr     x0, [sp], #16\n"           # If 0 (false), jump to end
                    program +=  "    cmp     x0, #0            ; check if false\n"
                    # program += f"    b.eq    .END_BRANCH_{_if}\n"
                    program += f"    b.eq    .ELSE_BRANCH_{_if}\n"
                    program +=  "    ; then branch\n"

                case 'W':
                    _while = control_stack[-1][-1]
                    program +=  "    ldr     x0, [sp], #16\n"           # If 0 (false), jump (exit) while loop
                    program +=  "    cmp     x0, #0\n"
                    program += f"    b.eq    .WHILE_END_{_while}\n"

                case _:
                    print(f"Internal error: Control-stack contains yunk: {control_stack[-1]}")
                    sys.exit(1)
            
            stack_depth -= 1
            tok_i += 1
        
        elif tok == "else":
            if stack_depth > initial_depth:
                print(f"Stack depth: {stack_depth} > (init){initial_depth}")
                program += f"    add     sp, sp, #{(stack_depth - initial_depth) * 16}\n"
                stack_depth = initial_depth

            if control_stack[-1][0] != 'I':
                print(f"Compilation Error: Unexpected 'else', missing associated 'if'\n\tFound: {control_stack[-1]}")
                sys.exit(1)

            _if = control_stack[-1][-1]
            program += f"    b    .END_BRANCH_{_if}\n"
            program += f".ELSE_BRANCH_{_if}:\n" # This is not needed I think, there will not be any branching here but i can be good to keep for now
            program +=  "    ; else branch\n"

            stack_depth = initial_depth
            tok_i += 1

        elif tok == "end":
            if stack_depth > initial_depth:
                print(f"Stack depth: {stack_depth} > (init){initial_depth}")
                program += f"    add     sp, sp, #{(stack_depth - initial_depth) * 16}\n"
                stack_depth = initial_depth

            match control_stack[-1][0]:
                case 'I':
                    _if = control_stack.pop()[-1]
                    program += f".END_BRANCH_{_if}:\n"
                    # program +=  "    mov    sp, x29\n"    Why is this here? - Question for Gemini

                case 'W':
                    _while = control_stack.pop()[-1]
                    program += f"    b       .WHILE_START_{_while}\n"
                    program += f".WHILE_END_{_while}:\n"
                    # program +=  "    mov    sp, x29\n"    Why is this here? - Question for Gemini

                case _:
                    print(f"Internal error: Control-stack contains yunk: {control_stack[-1]}")
                    sys.exit(1)

            if stack_depth != initial_depth:
                print(f"Stack inbalance! {stack_depth} > (init){initial_depth}")
                sys.exit(1)
                
            tok_i += 1
        
        elif tok[0] == '"': # String literal
            # get pointer from page
            # push pointer

            id = get_str_id(tok)
            if id < 0:
                print(f"ERROR: String literal has no matching id: {tok}")
                sys.exit(1)
            
            program += f"    adrp    x0, l_.STR.{id}@PAGE\n"
            program += f"    add     x0, x0, l_.STR.{id}@PAGEOFF\n"
            program +=  "    str     x0, [sp, #-16]!\n"

            type_stack.append("STR")
            
            stack_depth += 1
            tok_i += 1

        else:
            program += f"    mov     x0, #{tok}\n"
            program +=  "    str     x0, [sp, #-16]!\n"

            type_stack.append("INT")
            
            stack_depth += 1
            tok_i += 1

    return program

def gen_str_section_ARM(strings) -> str:
    section =  "l_.PRINT_NUMBER:\n"
    section += "    .asciz  \"%d\\12\\0\"\n"
    section += "l_.SCANF_255s_FMT:\n"
    section += "    .asciz  \"%255s\\0\"\n\n"

    str_lit_num = 0
    for string in strings:
        section += f"l_.STR.{str_lit_num}:\n"
        section += f"    .asciz  {string}\n"
        str_lit_num += 1
    
    return section

def gen_BSS_ARM() -> str:
    bss = ".zerofill __DATA,__bss,_io,256,0\n"
    return bss

if SIM:
    stack = []

    print("SIM not implemented yet!")
    """
    for tokens[tok_i] in tokens:
        if tokens[tok_i] ==  "print":
            print(stack.pop())
        elif tokens[tok_i] == "+":
            lhs = stack.pop()
            rhs = stack.pop()
            res = int(lhs) + int(rhs)
            stack.append(res)
        else:
            stack.append(tok)
    """

else:
    asm = ""
    program = ""

    architecture = platform.machine().lower()

    if "x86_64" in architecture or "amd64" in architecture:
        asm += f"    .file \"{sys.argv[1]}.s\"\n"

        """
            .text
            .section .rdata,"dr"
        .LC0:
            .ascii "Hello World!\12\0"
        .LC1:
            .ascii "Hello World2!\12\0"
        """

        program += """	.def	printf;	.scl	3;	.type	32;	.endef
        .seh_proc	printf
    printf:
        pushq	%rbp
        .seh_pushreg	%rbp
        pushq	%rbx
        .seh_pushreg	%rbx
        subq	$56, %rsp
        .seh_stackalloc	56
        leaq	48(%rsp), %rbp
        .seh_setframe	%rbp, 48
        .seh_endprologue
        movq	%rcx, 32(%rbp)
        movq	%rdx, 40(%rbp)
        movq	%r8, 48(%rbp)
        movq	%r9, 56(%rbp)
        leaq	40(%rbp), %rax
        movq	%rax, -16(%rbp)
        movq	-16(%rbp), %rbx
        movl	$1, %ecx
        movq	__imp___acrt_iob_func(%rip), %rax
        call	*%rax
        movq	%rax, %rcx
        movq	32(%rbp), %rax
        movq	%rbx, %r8
        movq	%rax, %rdx
        call	__mingw_vfprintf
        movl	%eax, -4(%rbp)
        movl	-4(%rbp), %eax
        addq	$56, %rsp
        popq	%rbx
        popq	%rbp
        ret
        .seh_endproc

        .section .rdata,"dr"
    .PRINT_NUMBER:
        .ascii "%d\\12\\0"

    """
        
        program += "    .text\n"
        program += "    .globl main\n"
        program += "    .def main\n"
        program += "main:\n"
        program += "    pushq   %rbp\n"
        program += "    movq    %rsp, %rbp\n"

        program += gen_asm_x86_64(tokens)

        program += "    movq    $0, %rax\n"
        program += "    popq    %rbp\n"
        program += "    ret\n"

        asm += program

        with open(f"{a_file}.s", "w") as f:
            # print(asm)
            f.write(asm)

        subprocess.run(["gcc", f"{a_file}.s", "-o", f"{o_file}.exe"])

    else:
        program += "    .section	__TEXT,__text,regular,pure_instructions\n"
        program += "    .globl _main\n"
        program += "    .p2align    2\n"
        program += "_main:\n"
        program += "    stp     x29, x30, [sp, #-16]!\n"
        program += "    mov     x29, sp\n"

        program += gen_asm_ARM(tokens)
        
        program += "    mov	    w0, #0\n"
        program += "    ldp     x29, x30, [sp], #16\n"
        program += "    ret\n\n"

        asm += program
        
        asm += "    .section    __TEXT,__cstring,cstring_literals\n"

        asm += gen_str_section_ARM(str_literals)
        asm += gen_BSS_ARM()
        
        with open(f"{a_file}.s", "w") as f:
            # print(asm)
            f.write(asm)

        subprocess.run(["gcc", f"{a_file}.s", "-o", f"{o_file}"])
