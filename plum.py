import os
import re
import sys
import platform
import argparse
import subprocess

# import plum_win_lin_x86_64
import plum_mac_arm

def parse_args():
    parser = argparse.ArgumentParser(
        prog="plum",
        description="Compile a .plum source file to a native executable.",
    )
    parser.add_argument("source", help="Path to the .plum source file")
    parser.add_argument(
        "--emit",
        dest="asm_file",
        metavar="FILE",
        help="Base path for the generated assembly (.s appended). "
             "Defaults to the source file's name.",
    )
    parser.add_argument(
        "-o",
        dest="out_file",
        metavar="FILE",
        help="Path for the compiled executable. Defaults to the source file's name.",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        parser.error(f"no such file: {args.source}")

    stem = os.path.splitext(os.path.basename(args.source))[0]

    asm_file = args.asm_file or stem
    if asm_file.endswith(".s"):        # tolerate "--emit foo.s" as well as "--emit foo"
        asm_file = asm_file[:-2]

    out_file = args.out_file or stem

    return args.source, asm_file, out_file

def read_file(file) -> str:
    with open(file, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    return source_code

def expand_macros(source_code):
    macros = {}
    
    macro_pattern = re.compile(r'^macro\s+(\w+)\s+(.*)$', re.MULTILINE)
    
    for match in macro_pattern.finditer(source_code):
        name = match.group(1)
        value = match.group(2)
        macros[name] = value
        
    clean_code = macro_pattern.sub('', source_code)
    
    def replace_match(match):
        macro_name = match.group(1)
        return macros.get(macro_name, match.group(0))
    
    expanded_code = re.sub(r'@(\w+)', replace_match, clean_code)
    return expanded_code, macros

def tokenize(source_code):
    STRING_REGEX = r'"[^"\n]*"'
    COMMENT_REGEX = re.compile(r'#[^\n]*')
    WHITESPACE_SPLIT = re.compile(r'[ \t\n]+')

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
            chunk = COMMENT_REGEX.sub('', chunk)
            sub_chunks = WHITESPACE_SPLIT.split(chunk)
            tokens.extend([t for t in sub_chunks if t])
    
    return tokens, str_literals

def is_integer(token):
    try:
        int(token)
        return True
    except ValueError:
        return False

s_file, a_file, o_file = parse_args()
source = read_file(s_file)
source_code, macros = expand_macros(source)
tokens, str_literals = tokenize(source_code)

# Operating System
os_type = platform.system().lower()
# CPU Architecture
architecture = platform.machine().lower()

Generator = None

if os_type == "darwin":
    if "arm64" in architecture or "aarch64" in architecture:
        from plum_mac_arm import Generator

    elif "x86_64" in architecture:
        raise NotImplementedError(f"macOS x86_64 is not implemented yet!")
    
elif os_type == "linux" or os_type == "windows":
    if "arm64" in architecture or "aarch64" in architecture:
        raise NotImplementedError(f"Linux/Windows ARM64 is not implemented yet!")
    elif "x86_64" in architecture:
        print("TODO: Windows/Linux x86_64")
        # from plum_win_lin_x86_64 import Generator
else:
    if "arm" in architecture:
        print(f"Not implemented yet!\n\tArchitecture: {architecture}\n\tOS: {os_type}")
    else:
        raise OSError(f"Unsupported OS/Architecture: {os_type} ({architecture})")

if Generator is None:
    raise RuntimeError("Generator was not loaded properly.")

generator = Generator(tokens, str_literals)
asm = generator.gen()

with open(f"{a_file}.s", "w") as f:
    f.write(asm)

subprocess.run(["gcc", f"{a_file}.s", "-o", f"{o_file}"])
