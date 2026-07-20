import os
import re
import sys
import ntpath
import platform
import argparse
import subprocess


def parse_args():
    raw_args = sys.argv[1:]
    build_flags = []
    if "--flags" in raw_args:
        idx = raw_args.index("--flags")
        build_flags = raw_args[idx + 1:]
        raw_args = raw_args[:idx]
 
    parser = argparse.ArgumentParser(
        prog="plum",
        description="Compile a .plum source file to a native executable.",
        epilog=(
            'Pass compiler/linker flags with --flags, placed last on the command line - '
            'everything after it is forwarded as-is, e.g.:\n'
            '  plum.py file.plum --emit ./asm -o ./out --flags -O2 -lraylib -framework OpenGL'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", help="Path to the .plum source file")
    parser.add_argument(
        "--emit",
        dest="asm_file",
        metavar="FILE",
        help="Base path for the generated assembly (.s appended). Defaults to the source file's name.",
    )
    parser.add_argument(
        "-o",
        dest="out_file",
        metavar="FILE",
        help="Path for the compiled executable. Defaults to the source file's name.",
    )
    args = parser.parse_args(raw_args)
 
    if not os.path.isfile(args.source):
        parser.error(f"no such file: {args.source}")
 
    stem = os.path.splitext(os.path.basename(args.source))[0]
 
    asm_file = args.asm_file or stem
    if asm_file.endswith(".s"):
        asm_file = asm_file[:-2]
 
    out_file = args.out_file or stem
 
    return args.source, asm_file, out_file, build_flags

COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))

def read_file(file) -> str:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    return content

def strip_comments(source) -> str:
    pattern = re.compile(r'("[^"\n]*")|#[^\n]*')
    return pattern.sub(lambda m: m.group(1) if m.group(1) is not None else '', source)

def resolve_imports(source, imported_files=None) -> str:
    if imported_files is None:
        imported_files = set()
    
    import_pattern = re.compile(r'^import\s+"([^"]+)"\s*$', re.MULTILINE)
    
    def replace_import(match):
        import_path = match.group(1)
        full_path = os.path.abspath(os.path.join(COMPILER_DIR, f"{import_path}.plum"))
        
        if full_path in imported_files:
            return ""
        
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Kunde inte hitta den importerade filen: {full_path}")
            
        imported_files.add(full_path)
        imported_content = strip_comments(read_file(full_path))
        return resolve_imports(imported_content, imported_files)
    
    return import_pattern.sub(replace_import, source)

def expand_macros(source) -> str:
    macros = {}
    macro_pattern = re.compile(r'^macro\s+(\w+)\s+(.*)$', re.MULTILINE)
    
    for match in macro_pattern.finditer(source):
        name = match.group(1)
        value = match.group(2)
        macros[name] = value
        
    clean_code = macro_pattern.sub('', source)
    
    macro_name = ""

    def replace_match(match):
        nonlocal macro_name
        macro_name = match.group(1)
        return macros.get(macro_name, match.group(0))
    
    expanded_code = clean_code
    max_depth = 100
    depth = 0
    
    while depth < max_depth:
        next_code = re.sub(r'@(\w+)', replace_match, expanded_code)
        if next_code == expanded_code:
            break
        expanded_code = next_code
        depth += 1
    else:
        raise RecursionError(
            f"Preprocessing Error: Recursive macro expands over maximum depth. Macro: {macro_name}"
        )
    
    return expanded_code, macros

def preprocess(source) -> str:
    clean_source = strip_comments(source)
    full_source = resolve_imports(clean_source)
    code, _macros = expand_macros(full_source)
    return code

def tokenize(source_code):
    STRING_REGEX = r'"[^"\n]*"'
    WHITESPACE_SPLIT = re.compile(r'\s+')

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
            sub_chunks = WHITESPACE_SPLIT.split(chunk)
            tokens.extend([t for t in sub_chunks if t])
    
    return tokens, str_literals

s_file, a_file, o_file, build_flags = parse_args()
source = read_file(s_file)
source_code = preprocess(source)
tokens, str_literals = tokenize(source_code)

# Operating System
os_type = platform.system().lower()
# CPU Architecture
architecture = platform.machine().lower()

Generator = None

# print(os_type, f"{architecture}")

if os_type == "darwin":
    if "arm64" in architecture or "aarch64" in architecture:
        from plum_mac_arm import Generator

    elif "x86_64" in architecture:
        raise NotImplementedError(f"macOS x86_64 is not implemented yet!")
    
elif os_type == "linux" or os_type == "windows":
    if "arm64" in architecture or "aarch64" in architecture:
        raise NotImplementedError(f"Linux/Windows ARM64 is not implemented yet!")
    elif "x86_64" or "amd64" in architecture:
        print("TODO: Windows/Linux x86_64")
        from plum_win_x86_64 import Generator
else:
    if "arm" in architecture:
        raise NotImplementedError(f"{os_type} ({architecture})\n")
    else:
        raise OSError(f"Unsupported OS/Architecture: {os_type} ({architecture})")

if Generator is None:
    raise RuntimeError("Generator was not loaded properly.")

filename = ntpath.basename(s_file)
generator = Generator(f"{filename}", tokens, str_literals)
asm = generator.gen()

with open(f"{a_file}.s", "w") as f:
    f.write(asm)

def try_compile(compiler):
    command = [compiler, f"{a_file}.s", "-o", o_file] + build_flags
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        return False, f"'{compiler}' not found on PATH"
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, None

last_error = None
for compiler in ("gcc", "clang"):
    ok, err = try_compile(compiler)
    if ok:
        break
    last_error = err
else:
    print(f"Failed to assemble program:\n{last_error}", file=sys.stderr)
    sys.exit(1)
