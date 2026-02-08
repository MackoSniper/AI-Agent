import os
import pickle
from config import WORKING_DIR
from google.genai import types # type: ignore[import]

# Ścieżka do pliku pamięci (wewnątrz workspace, żeby nie śmiecić)
MEMORY_FILE = os.path.join(WORKING_DIR, "session_state.pkl")

def load_memory():
    """Wczytuje historię rozmowy z pliku, jeśli istnieje."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'rb') as f:
                history = pickle.load(f)
                return history
        except Exception as e:
            print(f"⚠️ [MEMORY] Błąd odczytu pamięci: {e}. Zaczynam nową sesję.")
            return []
    return []

def save_memory(messages):
    """Zapisuje aktualną listę wiadomości do pliku."""
    try:
        with open(MEMORY_FILE, 'wb') as f:
            pickle.dump(messages, f)
    except Exception as e:
        print(f"⚠️ [MEMORY] Nie udało się zapisać stanu: {e}")

def clear_memory():
    """Czyści pamięć (usuwa plik sesji)."""
    if os.path.exists(MEMORY_FILE):
        os.remove(MEMORY_FILE)
        print("🧹 [MEMORY] Pamięć wyczyszczona. Nowa sesja.")