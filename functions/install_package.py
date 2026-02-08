import subprocess
import sys
from google.genai import types # type: ignore[import]

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

schema_install_package = types.FunctionDeclaration(
    name="install_package",
    description="Installs a Python package using pip. Use this if a required library is missing.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "package_name": types.Schema(
                type=types.Type.STRING,
                description="The name of the package to install (e.g., 'matplotlib')."
            ),
        },
        required=["package_name"]
    )
)