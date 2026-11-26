import os
import sys
import importlib.util
import inspect
import json

from config import WORKING_DIR, PROJECT_ROOT

# Where to look for tools?
STATIC_FUNCTIONS_DIR = os.path.join(PROJECT_ROOT, "functions")
DYNAMIC_FUNCTIONS_DIR = WORKING_DIR

# Global containers
function_map = {}
declarations = []

def load_tool_from_file(filepath):
    """
    Loads a .py file and looks in it for a function and its schema.
    Protected against duplicates and global-variable errors.
    """
    # === FIX: We must declare that we use global variables ===
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

        # Scan the module contents
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, dict) and obj.get("type") == "function" and "function" in obj:
                schema = obj
                tool_name = schema["function"]["name"]
                
                if hasattr(module, tool_name) and callable(getattr(module, tool_name)):
                    func = getattr(module, tool_name)
                    
                    # === DUPLICATE PROTECTION ===
                    # If the tool already exists, remove the old definition from the declarations list
                    if tool_name in function_map:
                        # Filter the global list, removing the old entry
                        declarations = [d for d in declarations if d["function"]["name"] != tool_name]

                    # Register the new version
                    function_map[tool_name] = func
                    declarations.append(schema)

    except Exception as e:
        print(f"  [LOADER] Error while loading {filename}: {e}")

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


# Initialization
available_tools = refresh_tools()


def get_tools():
    """Current list of tool schemas in OpenAI format (for the `tools=` parameter)."""
    return declarations


def _tool_message(tool_call_id, payload):
    return {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(payload, ensure_ascii=False, default=str)}


def call_function(tool_call, verbose=False):
    """Executes a tool. `tool_call` is a dict {"id", "function": {"name", "arguments"}}.
    Returns a "tool" role message ready to be appended to the history."""
    function_name = tool_call["function"]["name"] or ""
    call_id = tool_call["id"]

    if verbose:
        print(f" - Calling function: {function_name}")

    if function_name not in function_map:
        # Try refreshing the tools on the fly if the function is missing (optional)
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
