import os
from config import WORKING_DIR

def is_safe_path(path: str) -> bool:
    """
    Checks whether the given path is inside the defined WORKING_DIR.
    Prevents Directory Traversal attacks (np. ../../etc/passwd).
    """
    abs_working_dir = os.path.abspath(WORKING_DIR)
    
    abs_target_path = os.path.abspath(os.path.join(abs_working_dir, path))
    
    try:
        common = os.path.commonpath([abs_working_dir, abs_target_path])
        return common == abs_working_dir
    except ValueError:
        return False

def get_safe_path(path: str) -> str:
    """Returns the full path if it is safe, otherwise raises an error."""
    if not is_safe_path(path):
        raise PermissionError(f"ACCESS DENIED: Attempt to access outside the working folder: {path}")
    return os.path.abspath(os.path.join(WORKING_DIR, path))