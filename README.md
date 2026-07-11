<img height="128" alt="PLUM LOGO" src="./media/plum.png">

# Plum
Plum is a simple compiled arithmetic stackbased programming language written in Python.

> Note: Plum needs gcc on the system to assemble and link the generated assembly code. Full language only compiles to ARM right now, older code will run on x86_64.

### Build a .plum file

```
python plum.py <name/path to .plum file> <name/path for .s file> <name/path for executable>
```

### Syntax Overview

1. Any number will get pushed onto the stack, special case in while statement.
2. Operators consume (pop) values from the stack, use the 'dup' keyword to duplicate the top value.
3. 'if' and 'while' have the same condition and do blocks but the 'if' statement requires a matching 'else' even if it is empty.
4. Take user input with the '?' operator, the value is stored in a BSS buffer which address is pushed to the stack.

### Arithmetic
```
10 5 + print --> 15
10 5 - print --> 5
10 5 * print --> 50
10 5 / print --> 2
10 5 % print --> 0
```

### Duplicate
```
1 dup + print --> 2
```

### Swap

```
10 20 swap - --> 10
```

### If
```
0
if
    dup 1 ==
do
    "True" print
else
    "False" print
end

Output:
"False"
```

### Loop
```
0
while
    dup 10 <
do
    dup .
    1 +
end

Output:
1
2
3
4
5
6
7
8
9
```

### IO
```
1
while
    dup 1 ==
do
    ? print
end

Output:
Hello
Hello
```
