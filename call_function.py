import os
import sys
import importlib.util
import inspect
from google.genai import types  # type: ignore[import]

from config import WORKING_DIR, PROJECT_ROOT

# Gdzie szukać narzędzi?
STATIC_FUNCTIONS_DIR = os.path.join(PROJECT_ROOT, "functions")
DYNAMIC_FUNCTIONS_DIR = WORKING_DIR

# Globalne kontenery
function_map = {}
declarations = []

def load_tool_from_file(filepath):
    """
    Ładuje plik .py, szuka w nim funkcji i schematu.
    Zabezpieczone przed duplikatami i błędami zmiennych globalnych.
    """
    # === POPRAWKA: Musimy zadeklarować, że używamy zmiennych globalnych ===
    global declarations, function_map 
    
    filename = os.path.basename(filepath)
    module_name = os.path.splitext(filename)[0]
    
    if filename.startswith("__") or module_name == "security_utils" or not filename.endswith(".py"):
        return

    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Skanowanie zawartości modułu
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, types.FunctionDeclaration):
                schema = obj
                tool_name = schema.name
                
                if hasattr(module, tool_name) and callable(getattr(module, tool_name)):
                    func = getattr(module, tool_name)
                    
                    # === ZABEZPIECZENIE PRZED DUPLIKATAMI ===
                    # Jeśli narzędzie już istnieje, usuwamy starą definicję z listy declarations
                    if tool_name in function_map:
                        # Filtrujemy listę globalną, usuwając stary wpis
                        declarations = [d for d in declarations if d.name != tool_name]

                    # Rejestracja nowej wersji
                    function_map[tool_name] = func
                    declarations.append(schema)

    except Exception as e:
        print(f"  [LOADER] Błąd przy ładowaniu {filename}: {e}")

def refresh_tools():
    global declarations, function_map
    declarations.clear()
    function_map.clear()

    if os.path.exists(STATIC_FUNCTIONS_DIR):
        for filename in os.listdir(STATIC_FUNCTIONS_DIR):
            load_tool_from_file(os.path.join(STATIC_FUNCTIONS_DIR, filename))

    if os.path.exists(DYNAMIC_FUNCTIONS_DIR):
        for filename in os.listdir(DYNAMIC_FUNCTIONS_DIR):
            load_tool_from_file(os.path.join(DYNAMIC_FUNCTIONS_DIR, filename))

    return types.Tool(function_declarations=declarations)

# Inicjalizacja
available_functions_tool = refresh_tools() 


def call_function(function_call, verbose=False):
    if verbose:
        print(f" - Calling function: {function_call.name}")

    function_name = function_call.name or ""
    
    if function_name not in function_map:
        # Próba odświeżenia narzędzi w locie, jeśli funkcji nie ma (opcjonalne)
        refresh_tools()
        if function_name not in function_map:
            return types.Content(
                role="tool",
                parts=[types.Part.from_function_response(
                    name=function_name,
                    response={"error": f"Unknown function: {function_name}"},
                )],
            )

    args = dict(function_call.args) if function_call.args else {}
    
    func_obj = function_map[function_name]
    sig = inspect.signature(func_obj)
    
    if "working_directory" in sig.parameters:
        args["working_directory"] = WORKING_DIR

    try:
        result = func_obj(**args)
        return types.Content(
            role="tool",
            parts=[types.Part.from_function_response(
                name=function_name,
                response={"result": result},
            )],
        )
    except Exception as e:
        return types.Content(
            role="tool",
            parts=[types.Part.from_function_response(
                name=function_name,
                response={"error": f"Function execution failed: {str(e)}"},
            )],
        )