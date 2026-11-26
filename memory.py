import json
import os
from config import WORKING_DIR

# The conversation history is a list of plain dicts in OpenAI format, so we save it as JSON
# (provider-independent; it can be switched mid-session).
MEMORY_FILE = os.path.join(WORKING_DIR, "session_state.json")
LEGACY_MEMORY_FILE = os.path.join(WORKING_DIR, "session_state.pkl")  # old Gemini format, unreadable by the new code


def load_memory():
    """Loads the conversation history from a file, if it exists."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [MEMORY] Failed to read memory: {e}. Starting a new session.")
    return []


def save_memory(messages):
    """Saves the current list of messages to a file."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to save state: {e}")


def clear_memory():
    """Clears memory (removes the session file)."""
    cleared = False
    for path in (MEMORY_FILE, LEGACY_MEMORY_FILE):
        if os.path.exists(path):
            os.remove(path)
            cleared = True
    if cleared:
        print("🧹 [MEMORY] Memory cleared. New session.")
