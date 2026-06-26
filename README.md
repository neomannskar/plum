# plum
Plum is a simple compiled arithmetic stackbased programming language written in Python.

> Note: Plum needs gcc on the system to assemble and link the generated assembly code. Only compiles to x86_64 right now.

### Syntax Overview

1. Any number will get pushed onto the stack, special case in while statement.
2. Operators consume (pop) values from the stack, use the 'dup' keyword to duplicate the top value.
3. Print to the terminal with the '.' operator.

### Arithmetic
```
10 5 + .
10 5 - .
10 5 * .
10 5 / . 
```

### Loop
```
0
while
    dup 10 <
do
    1 +
    dup .
end
```
