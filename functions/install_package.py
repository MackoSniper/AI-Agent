import subprocess
import sys

def install_package(package_name):
    """
    Installs a Python package using pip in the current environment.
    """
    try:
        # Używamy sys.executable, aby instalować w TYM SAMYM środowisku
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return f"Successfully installed '{package_name}'."
    except subprocess.CalledProcessError as e:
        return f"Error installing '{package_name}': {e}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"


# Schemat narzędzia w formacie OpenAI (działa u wszystkich dostawców; working_directory jest wstrzykiwany automatycznie)
schema_install_package = {
    "type": "function",
    "function": {
        "name": "install_package",
        "description": "Installs a Python package using pip. Use this if a required library is missing.",
        "parameters": {
            "type": "object",
            "properties": {
                "package_name": {
                    "type": "string",
                    "description": "The name of the package to install (e.g., 'matplotlib')."
                }
            },
            "required": [
                "package_name"
            ]
        }
    }
}
