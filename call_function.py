import os
import sys
import importlib.util
import inspect
import json

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
            if isinstance(obj, dict) and obj.get("type") == "function" and "function" in obj:
                schema = obj
                tool_name = schema["function"]["name"]
                
                if hasattr(module, tool_name) and callable(getattr(module, tool_name)):
                    func = getattr(module, tool_name)
                    
                    # === ZABEZPIECZENIE PRZED DUPLIKATAMI ===
                    # Jeśli narzędzie już istnieje, usuwamy starą definicję z listy declarations
                    if tool_name in function_map:
                        # Filtrujemy listę globalną, usuwając stary wpis
                        declarations = [d for d in declarations if d["function"]["name"] != tool_name]

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

    return declarations


# Inicjalizacja
available_tools = refresh_tools()


def get_tools():
    """Aktualna lista schematów narzędzi w formacie OpenAI (do parametru `tools=`)."""
    return declarations


def _tool_message(tool_call_id, payload):
    return {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(payload, ensure_ascii=False, default=str)}


def call_function(tool_call, verbose=False):
    """Wykonuje narzędzie. `tool_call` to słownik {"id", "function": {"name", "arguments"}}.
    Zwraca wiadomość roli "tool" gotową do dopisania do historii."""
    function_name = tool_call["function"]["name"] or ""
    call_id = tool_call["id"]

    if verbose:
        print(f" - Calling function: {function_name}")

    if function_name not in function_map:
        # Próba odświeżenia narzędzi w locie, jeśli funkcji nie ma (opcjonalne)
        refresh_tools()
        if function_name not in function_map:
            return _tool_message(call_id, {"error": f"Unknown function: {function_name}"})

    try:
        args = json.loads(tool_call["function"].get("arguments") or "{}")
    except json.JSONDecodeError as e:
        return _tool_message(call_id, {"error": f"Invalid JSON arguments: {e}"})

    func_obj = function_map[function_name]
    sig = inspect.signature(func_obj)

    if "working_directory" in sig.parameters:
        args["working_directory"] = WORKING_DIR

    try:
        return _tool_message(call_id, {"result": func_obj(**args)})
    except Exception as e:
        return _tool_message(call_id, {"error": f"Function execution failed: {str(e)}"})
