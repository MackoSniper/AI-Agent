"""Chat storage: every conversation is a JSON file in agent_workspace/chats/.

A chat is a list of plain dicts in OpenAI message format, so it is provider-independent
(a chat can be continued with a different provider). `index.json` keeps the title and
last-update time of every chat so the sidebar list does not have to open the (possibly big) chat files.

The "active" chat (id stored in chats/active) is shared by the Streamlit app and the CLI:
`main.py` continues whatever chat is active, and `--new` starts a fresh one.
"""
import json
import os
import re
import time
import uuid

from config import WORKING_DIR

CHATS_DIR = os.path.join(WORKING_DIR, "chats")
INDEX_FILE = os.path.join(CHATS_DIR, "index.json")
ACTIVE_FILE = os.path.join(CHATS_DIR, "active")
LEGACY_FILE = os.path.join(WORKING_DIR, "session_state.json")  # single-session storage used before chat history
LEGACY_PKL = os.path.join(WORKING_DIR, "session_state.pkl")    # old Gemini format, unreadable by the new code

TITLE_LENGTH = 40
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# --- helpers ---------------------------------------------------------------

def _chat_path(chat_id):
    if not _ID_RE.match(chat_id or ""):
        raise ValueError(f"Invalid chat id: {chat_id!r}")
    return os.path.join(CHATS_DIR, f"{chat_id}.json")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to read {os.path.basename(path)}: {e}")
        return default


def _write_json(path, data):
    os.makedirs(CHATS_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # atomic: a crash cannot leave a half-written chat


def _title_from(messages):
    """Title = start of the first user message (text, or a label for images / voice)."""
    for m in messages:
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            text = content
        else:
            parts = content or []
            text = " ".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
            if not text or text.startswith(("Listen to this recording", "Look at the attached image")):
                text = "🎙️ Voice message" if any(p.get("type") == "input_audio" for p in parts) else "🖼️ Image"
        text = " ".join(text.split())
        if text:
            return text if len(text) <= TITLE_LENGTH else text[:TITLE_LENGTH - 1] + "…"
    return "New chat"


def _migrate_legacy():
    """Turns the old single session file into a regular chat (once)."""
    if not os.path.exists(LEGACY_FILE):
        return
    messages = _read_json(LEGACY_FILE, [])
    if messages:
        chat_id = new_chat_id()
        save_chat(chat_id, messages)
        if not os.path.exists(ACTIVE_FILE):
            set_active_chat(chat_id)
    os.remove(LEGACY_FILE)


# --- chats -----------------------------------------------------------------

def new_chat_id():
    """A fresh chat id. Nothing is written until the first message is saved, so empty chats never pile up."""
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def list_chats():
    """Saved chats, newest first: [{"id", "title", "updated"}]."""
    _migrate_legacy()
    index = _read_json(INDEX_FILE, {})
    chats = [{"id": cid, **meta} for cid, meta in index.items() if os.path.exists(_chat_path(cid))]
    return sorted(chats, key=lambda c: c.get("updated", 0), reverse=True)


def load_chat(chat_id):
    return _read_json(_chat_path(chat_id), [])


def save_chat(chat_id, messages):
    _write_json(_chat_path(chat_id), messages)
    index = _read_json(INDEX_FILE, {})
    index[chat_id] = {"title": _title_from(messages), "updated": time.time()}
    _write_json(INDEX_FILE, index)


def delete_chat(chat_id):
    path = _chat_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
    index = _read_json(INDEX_FILE, {})
    if index.pop(chat_id, None) is not None:
        _write_json(INDEX_FILE, index)


def get_active_chat():
    """Id of the active chat: the stored one, else the most recent chat, else a fresh id."""
    _migrate_legacy()
    try:
        with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
            chat_id = f.read().strip()
        if _ID_RE.match(chat_id):
            return chat_id
    except FileNotFoundError:
        pass
    chats = list_chats()
    chat_id = chats[0]["id"] if chats else new_chat_id()
    set_active_chat(chat_id)  # remember it, so repeated calls (load, then save) agree on the id
    return chat_id


def set_active_chat(chat_id):
    _chat_path(chat_id)  # validates the id
    os.makedirs(CHATS_DIR, exist_ok=True)
    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(chat_id)


# --- API used by the CLI (main.py): works on the active chat ------------------

def load_memory():
    """Loads the history of the active chat."""
    return load_chat(get_active_chat())


def save_memory(messages):
    """Saves the history of the active chat."""
    try:
        save_chat(get_active_chat(), messages)
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to save state: {e}")


def clear_memory():
    """Starts a fresh chat. The previous chat stays in the history."""
    set_active_chat(new_chat_id())
    print("🧹 [MEMORY] Started a new chat (the previous one is kept in the history).")
