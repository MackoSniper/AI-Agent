import json
import os
from config import WORKING_DIR

# Historia rozmowy to lista zwykłych słowników w formacie OpenAI, więc zapisujemy ją jako JSON
# (niezależnie od dostawcy; można ją przełączyć w trakcie sesji).
MEMORY_FILE = os.path.join(WORKING_DIR, "session_state.json")
LEGACY_MEMORY_FILE = os.path.join(WORKING_DIR, "session_state.pkl")  # stary format Gemini, nieczytelny dla nowego kodu


def load_memory():
    """Wczytuje historię rozmowy z pliku, jeśli istnieje."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [MEMORY] Błąd odczytu pamięci: {e}. Zaczynam nową sesję.")
    return []


def save_memory(messages):
    """Zapisuje aktualną listę wiadomości do pliku."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"⚠️ [MEMORY] Nie udało się zapisać stanu: {e}")


def clear_memory():
    """Czyści pamięć (usuwa plik sesji)."""
    cleared = False
    for path in (MEMORY_FILE, LEGACY_MEMORY_FILE):
        if os.path.exists(path):
            os.remove(path)
            cleared = True
    if cleared:
        print("🧹 [MEMORY] Pamięć wyczyszczona. Nowa sesja.")
