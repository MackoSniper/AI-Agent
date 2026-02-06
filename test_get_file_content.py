from functions.get_file_content import get_file_content  # type: ignore[import]

def main():
    result = get_file_content("calculator", "lorem.txt")
    size = len(result)
    if '[...File "lorem.txt" truncated at 10000 characters]' in result:
        print(f'{size} + File content was truncated as expected.')

    result = get_file_content("calculator", "main.py")
    print(result)

    result = get_file_content("calculator", "pkg/calculator.py")
    print(result)

    result = get_file_content("calculator", "/bin/cat")
    print(result)

    result = get_file_content("calculator", "pkg/does_not_exist.py")
    print(result)
if __name__ == "__main__":
    main()