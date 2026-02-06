from functions.get_files_info import get_files_info  # type: ignore[import]

def main():
    result = get_files_info("calculator", ".")
    print("Result for current directory:")
    print("  " + result.replace("\n", "\n  "))

    result = get_files_info("calculator", "pkg")
    print("Result for 'pkg' directory:")
    print("  " + result.replace("\n", "\n  "))

    result = get_files_info("calculator", "/bin")
    print("Result for '/bin' directory:")
    print("  " + result.replace("\n", "\n  "))

    result = get_files_info("calculator", "../")
    print("Result for '../' directory:")
    print("  " + result.replace("\n", "\n  "))

if __name__ == "__main__":
    main()