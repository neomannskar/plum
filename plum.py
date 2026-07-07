import re
import sys
import platform
import subprocess

SIM = False

lines = []

STRING_REGEX = r'"[^"\n]*"'

# python plum.py <.plum file> <.s file> <program>

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

        if tok == ".":
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
    control_stack = []
    type_stack = []

    while tok_i < len(tokens):
        tok = tokens[tok_i]

        if tok == ".":
            t = type_stack.pop()

            if t == "INT":
                # Load format string address into x0 (first argument)
                program += "    adrp    x0, l_.PRINT_NUMBER@PAGE\n"
                program += "    add     x0, x0, l_.PRINT_NUMBER@PAGEOFF\n"
                # Call printf (bl instead of call)
                program += "    bl      _printf\n"
                # Due to Mac ABI
                program += "    add     sp, sp, #16\n"

            elif t == "STR":
                program += "    ldr    x0, [sp], #16\n"
                program += "    bl      _puts\n"

            else:
                print("Internal Error: Unknown strlit in type_stack")
                sys.exit(0)

            tok_i += 1

        elif tok == "dup":
            if len(type_stack) > 0:
                t = type_stack[-1]
                type_stack.append(t)
            else:
                print("Compilation Error: 'dup' expects at least one value on the stack")
                sys.exit(1)

            program += "    ldr     x0, [sp]\n"
            program += "    str     x0, [sp, #-16]!\n"
            tok_i += 1

        elif tok == "+":
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '+' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)

            program += "    ldr     x0, [sp], #16\n"  # pop x0
            program += "    ldr     x1, [sp], #16\n"  # pop x1
            program += "    add     x0, x1, x0\n"
            program += "    str     x0, [sp, #-16]!\n" # push result
            tok_i += 1

            type_stack.append("INT")

        elif tok == "-":
            if len(type_stack) > 1:
                t1 = type_stack.pop()
                t2 = type_stack.pop()
                if t1 != "INT" or t2 != "INT":
                    print("Compilation Error: '-' expects two integers")
                    print("\t- Pointer arithmetic not implemented yet\n")
                    sys.exit(1)

            program += "    ldr     x1, [sp], #16\n"  # pop rbx equivalent (divisor/subtrahend)
            program += "    ldr     x0, [sp], #16\n"  # pop rax equivalent (minuend)
            program += "    sub     x0, x0, x1\n"
            program += "    str     x0, [sp, #-16]!\n"
            tok_i += 1

            type_stack.append("INT")

        elif tok == '*':
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
            tok_i += 1

            type_stack.append("INT")

        elif tok == '/':
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
            tok_i += 1

            type_stack.append("INT")

        elif tok == "while":
            program += f".WHILE_START_{while_counter}:\n"
            control_stack.append(while_counter)
            while_counter += 1
            tok_i += 1

        elif tok == "<":
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
            tok_i += 1
            
            type_stack.append("INT")

        elif tok == "do":
            if len(type_stack) > 0:
                t1 = type_stack.pop()
                if t1 != "INT":
                    print("Compilation Error: 'do' expects one integer")
                    sys.exit(1)
                
            current_while = control_stack[-1]
            program +=  "    ldr     x0, [sp], #16\n"
            program +=  "    cmp     x0, #0\n"
            program += f"    b.eq    .WHILE_END_{current_while}\n"
            tok_i += 1

        elif tok == "end":
            current_while = control_stack.pop()
            program += f"    b       .WHILE_START_{current_while}\n"
            program += f".WHILE_END_{current_while}:\n"
            program +=  "    mov    sp, x29\n"
            tok_i += 1
        
        elif tok[0] == '"': # String literal
            # get pointer from page
            # push pointer

            id = get_str_id(tok)
            if id < 0:
                print("ERROR: String literal has no matching id")
                sys.exit(1)
            
            program += f"    adrp    x0, l_.str.{id}@PAGE\n"
            program += f"    add x0, x0, l_.str.{id}@PAGEOFF\n"
            program +=  "    str     x0, [sp, #-16]!\n"
            tok_i += 1

            type_stack.append("STR")

        else:
            program += f"    mov     x0, #{tok}\n"
            program +=  "    str     x0, [sp, #-16]!\n"
            tok_i += 1

            type_stack.append("INT")

    return program

def gen_str_section_ARM(strings) -> str:
    section =  "l_.PRINT_NUMBER:\n"
    section += "    .asciz  \"%d\\12\\0\"\n\n"

    str_lit_num = 0
    for string in strings:
        section += f"l_.str.{str_lit_num}:\n"
        section += f"    .asciz  {string}\n"
        str_lit_num += 1
    
    return section

stack = []

if SIM:
    print("SIM not implemented yet!")
    """
    for tokens[tok_i] in tokens:
        if tokens[tok_i] == ".":
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
            print(asm)
            f.write(asm)

        subprocess.run(["gcc", f"{a_file}.s", "-o", f"{o_file}.exe"])

    else:
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
        
        with open(f"{a_file}.s", "w") as f:
            print(asm)
            f.write(asm)

        subprocess.run(["gcc", f"{a_file}.s", "-o", f"{o_file}"])
