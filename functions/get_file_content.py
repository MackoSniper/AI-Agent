import os
from config import MAX_CHARS
from google.genai import types  # type: ignore[import]

def get_file_content(working_directory, file_path):
    try:   
        working_dir_abs = os.path.abspath(working_directory)
        # Zmieniam nazwę zmiennej na target_path, bo to plik, a nie katalog
        target_path = os.path.normpath(os.path.join(working_dir_abs, file_path))
        
        # Zabezpieczenie przed wyjściem poza katalog (Path Traversal) - TO JEST DOBRZE
        if os.path.commonpath([working_dir_abs, target_path]) != working_dir_abs:
            return f'Error: Cannot read "{file_path}" as it is outside the permitted working directory'
        
        if not os.path.isfile(target_path):
            return f'Error: File not found or is not a regular file: "{file_path}"'
        
        # --- POPRAWKA: Dodanie encoding i errors ---
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(MAX_CHARS)
            # Sprawdzenie, czy jest coś więcej
            if f.read(1):
                content += f'\n[...File "{file_path}" truncated at {MAX_CHARS} characters...]'
        
        return content
    
    except Exception as e:
        return f"Error: reading file: {str(e)}"
    

schema_get_file_content = types.FunctionDeclaration(
    name="get_file_content",
    description="Retrieves the content of a specified file relative to the working directory",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="File path to read content from, relative to the working directory",
            ),
        },
        required=["file_path"], # Warto dodać
    ),
)