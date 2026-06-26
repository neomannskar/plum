import subprocess

SIM = False

lines = []

with open("test.eri") as f:
    raw = f.readlines()
    for line in raw:
        lines.append(line.strip())

tokens = []

for line in lines:
    tokens.extend(line.split())

tok_i = 0

def generate_asm(tokens) -> str:
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

        else:
            # It's an integer literal
            program += f"    pushq   ${tok}\n"
            tok_i += 1

    return program

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

    asm += "    .file \"a.s\"\n"

    """
        .text
        .section .rdata,"dr"
    .LC0:
        .ascii "Hello World!\12\0"
    .LC1:
        .ascii "Hello World2!\12\0"
    """
    
    program = ""

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

    program += generate_asm(tokens)

    program += "    movq    $0, %rax\n"
    program += "    popq    %rbp\n"
    program += "    ret\n"

    asm += program

    with open("a.s", "w") as f:
        print(asm)
        f.write(asm)

    subprocess.run(["gcc", "a.s", "-o", "output.exe"])
