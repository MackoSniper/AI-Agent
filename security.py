RISKY_FUNCTIONS = {"run_python_file", "write_file"}


def is_risky(function_name):
    return function_name in RISKY_FUNCTIONS


def confirm_execution(function_name, args):
    print(f"\n[SECURITY WARNING] The agent wants to execute a risky function: {function_name}")
    print(f"Arguments: {args}")
    response = input("Do you want to allow this execution? (y/N): ").strip().lower()
    return response == 'y'
