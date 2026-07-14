import os
import subprocess
import sys

TESTS_DIR = "./tests"
ASSEMBLY_DIR = "./assembly"
BUILD_DIR = "./build"

GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

def run_tests():
    os.makedirs(ASSEMBLY_DIR, exist_ok=True)
    os.makedirs(BUILD_DIR, exist_ok=True)

    if not os.path.exists(TESTS_DIR):
        print(f"{RED}{BOLD}Error:{RESET} Failed to find test directory '{TESTS_DIR}'!")
        sys.exit(1)

    test_files = [f for f in os.listdir(TESTS_DIR) if f.endswith(".plum")]

    if not test_files:
        print(f"{BLUE}Found no .plum files in '{TESTS_DIR}'.{RESET}")
        return

    print(f"{BLUE}{BOLD}Found {len(test_files)} test files. Compiling & Running...{RESET}\n")

    passed = 0
    failed = []

    for test_file in sorted(test_files):
        base_name = os.path.splitext(test_file)[0]
        
        input_path = os.path.join(TESTS_DIR, test_file)
        assembly_path = os.path.join(ASSEMBLY_DIR, base_name)
        output_path = os.path.join(BUILD_DIR, base_name)

        compile_cmd = [
            "python", "plum.py",
            input_path,
            "--emit", assembly_path,
            "-o", output_path
        ]

        print(f"-> Compiling: {' '.join(compile_cmd)}")
        compile_result = subprocess.run(compile_cmd, capture_output=True, text=True)

        if compile_result.returncode != 0:
            print(f"{RED}  [FAIL] {test_file} (Compilation failed){RESET}")
            if compile_result.stderr:
                print(f"{RED}         Compiler Error:\n{compile_result.stderr.strip()}{RESET}")
            elif compile_result.stdout:
                print(f"{RED}         Compiler Output:\n{compile_result.stdout.strip()}{RESET}")
            print()
            failed.append(input_path)
            continue

        run_cmd = [output_path]
        print(f"-> Running: {' '.join(run_cmd)}")
        
        try:
            run_result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=5)
            
            if run_result.returncode == 0:
                print(f"{GREEN}  [PASS] {test_file} (Compiled and ran successfully){RESET}\n")
                passed += 1
            else:
                print(f"{RED}  [FAIL] {test_file} (Program exited with code {run_result.returncode}){RESET}")
                if run_result.stdout:
                    print(f"{RED}         Program stdout:\n{run_result.stdout.strip()}{RESET}")
                if run_result.stderr:
                    print(f"{RED}         Program stderr:\n{run_result.stderr.strip()}{RESET}")
                print()
                failed.append(input_path)
                
        except subprocess.TimeoutExpired:
            print(f"{RED}  [FAIL] {test_file} (Program execution timed out after 5 seconds!){RESET}\n")
            failed.append(input_path)
        except Exception as e:
            print(f"{RED}  [FAIL] {test_file} (Could not execute binary: {e}){RESET}\n")
            failed.append(input_path)

    print("-" * 40)
    failed_len = len(failed)
    if failed_len == 0:
        print(f"{GREEN}{BOLD}ALL TESTS SUCCEEDED! ({passed}/{passed}){RESET}")
    else:
        print(f"{RED}{BOLD}SOME TESTS FAILED!{RESET}")
        for fail in failed:
            print(f"\t{fail}")
        print(f"{GREEN}Succeeded: {passed}{RESET} | {RED}Failed: {failed_len}{RESET}")
    print("-" * 40)

if __name__ == "__main__":
    run_tests()