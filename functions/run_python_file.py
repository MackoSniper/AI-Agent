import os
import subprocess
import sys  

def run_python_file(working_directory, file_path, args=None):
    try:   
        working_dir_abs = os.path.abspath(working_directory)
        absolute_file_path = os.path.normpath(os.path.join(working_dir_abs, file_path))
        
        valid_target_dir = os.path.commonpath([working_dir_abs, absolute_file_path]) == working_dir_abs

        if not valid_target_dir:
            return f'Error: Cannot execute "{file_path}" as it is outside the permitted working directory'
        
        if not os.path.isfile(absolute_file_path):
            return f'Error: "{file_path}" does not exist or is not a regular file'
        
        command = [sys.executable, absolute_file_path]
        if args:
            command.extend(args)
            
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            cwd=working_dir_abs, 
            timeout=30,
            encoding='utf-8',
            errors='replace' 
        )

        lines = []

        if result.returncode != 0:
            lines.append(f"Exit Code: {result.returncode}")

        if result.stdout:
            stdout = result.stdout.strip()
            if stdout:
                lines.append(f"STDOUT:\n{stdout}")
        
        if result.stderr:
            stderr_text = result.stderr.strip()
            if stderr_text:
                lines.append(f"STDERR:\n{stderr_text}")
        
        if not lines:
            lines.append("Script executed successfully but produced no output.")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out after 30 seconds. Infinite loop suspected."
        
    except Exception as e:
        return f"Error: executing Python file: {e}"


# Tool schema in OpenAI format (works with all providers; working_directory is injected automatically)
schema_run_python_file = {
    "type": "function",
    "function": {
        "name": "run_python_file",
        "description": "Executes a Python file located in the working directory and captures its output",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to the Python file to execute, relative to the working directory"
                },
                "args": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Optional list of arguments to pass to the Python script"
                }
            },
            "required": [
                "file_path"
            ]
        }
    }
}
