import os
import subprocess
from google.genai import types  # type: ignore[import]

def run_python_file(working_directory, file_path, args=None):
    try:   
        working_dir_abs = os.path.abspath(working_directory)
        absolute_file_path = os.path.normpath(os.path.join(working_dir_abs, file_path))
        valid_target_dir = os.path.commonpath([working_dir_abs, absolute_file_path]) == working_dir_abs

        if not valid_target_dir:
            return f'Error: Cannot execute "{file_path}" as it is outside the permitted working directory'
        
        if not os.path.isfile(absolute_file_path):
            return f'Error: "{file_path}" does not exist or is not a regular file'
        
        if not absolute_file_path.endswith(".py"):
            return f'Error: "{file_path}" is not a Python file'
        
        command = ["python", absolute_file_path]
        if args:
            command.extend(args)
        result = subprocess.run(command, capture_output=True, text=True, cwd=working_dir_abs, timeout=30)

        lines = []

        if result.returncode != 0:
            lines.append(f"Process exited with code {result.returncode}")

        if result.stdout:
            stdout = result.stdout.strip()
            if stdout:
                lines.append(f"STDOUT: {stdout}")
        
        if result.stderr:
            stderr_text = result.stderr.strip()
            if stderr_text:
                lines.append(f"STDERR: {stderr_text}")
        
        if not lines:
            lines.append("No output produced")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: executing Python file: {e}"
    

schema_run_python_file = types.FunctionDeclaration(
    name="run_python_file",
    description="Executes a Python file located in the working directory and captures its output",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="File path to the Python file to execute, relative to the working directory",
            ),
            "args": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.STRING,
                ),
                description="Optional list of arguments to pass to the Python script",
            ),
        },
    ),
)