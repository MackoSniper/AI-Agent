import os
from config import WORKING_DIR

def is_safe_path(path: str) -> bool:
    """
    Sprawdza, czy podana ścieżka znajduje się wewnątrz zdefiniowanego WORKING_DIR.
    Zapobiega atakom typu Directory Traversal (np. ../../etc/passwd).
    """
    abs_working_dir = os.path.abspath(WORKING_DIR)
    
    abs_target_path = os.path.abspath(os.path.join(abs_working_dir, path))
    
    try:
        common = os.path.commonpath([abs_working_dir, abs_target_path])
        return common == abs_working_dir
    except ValueError:
        return False

def get_safe_path(path: str) -> str:
    """Zwraca pełną ścieżkę jeśli jest bezpieczna, w przeciwnym razie rzuca błąd."""
    if not is_safe_path(path):
        raise PermissionError(f"ACCESS DENIED: Próba dostępu poza folder roboczy: {path}")
    return os.path.abspath(os.path.join(WORKING_DIR, path))