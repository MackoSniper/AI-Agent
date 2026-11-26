import json
import os

import pytest

import memory


@pytest.fixture(autouse=True)
def chat_dir(tmp_path, monkeypatch):
    chats = tmp_path / "chats"
    monkeypatch.setattr(memory, "CHATS_DIR", str(chats))
    monkeypatch.setattr(memory, "INDEX_FILE", str(chats / "index.json"))
    monkeypatch.setattr(memory, "ACTIVE_FILE", str(chats / "active"))
    monkeypatch.setattr(memory, "LEGACY_FILE", str(tmp_path / "session_state.json"))
    return tmp_path


def user(text):
    return {"role": "user", "content": text}


def test_save_and_load_roundtrip():
    memory.save_chat("a1", [user("hello"), {"role": "assistant", "content": "hi"}])
    assert memory.load_chat("a1")[1]["content"] == "hi"


def test_missing_chat_is_empty():
    assert memory.load_chat("nope") == []


def test_list_is_newest_first_with_titles(monkeypatch):
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(memory.time, "time", lambda: next(times))
    memory.save_chat("old", [user("first chat")])
    memory.save_chat("new", [user("second chat")])
    memory.save_chat("old", [user("first chat"), user("again")])  # touching it moves it to the top
    assert [(c["id"], c["title"]) for c in memory.list_chats()] == [("old", "first chat"), ("new", "second chat")]


def test_title_is_truncated_and_handles_attachments():
    memory.save_chat("long", [user("x" * 100)])
    memory.save_chat("img", [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "Look at the attached image(s) and describe them."}]}])
    memory.save_chat("voice", [{"role": "user", "content": [
        {"type": "input_audio", "input_audio": {"data": "AA", "format": "wav"}},
        {"type": "text", "text": "Listen to this recording and carry out the instruction."}]}])
    titles = {c["id"]: c["title"] for c in memory.list_chats()}
    assert len(titles["long"]) == memory.TITLE_LENGTH and titles["long"].endswith("…")
    assert titles["img"] == "🖼️ Image" and titles["voice"] == "🎙️ Voice message"


def test_delete_removes_chat_from_list_and_disk():
    memory.save_chat("gone", [user("bye")])
    memory.delete_chat("gone")
    assert memory.list_chats() == [] and memory.load_chat("gone") == []
    memory.delete_chat("gone")  # deleting twice is harmless


def test_invalid_ids_are_rejected():
    for bad in ("../evil", "a/b", "", "a.b"):
        with pytest.raises(ValueError):
            memory.load_chat(bad)


def test_active_chat_is_stable_and_persisted():
    first = memory.get_active_chat()      # nothing saved yet: fresh id, remembered
    assert memory.get_active_chat() == first
    memory.save_chat("c1", [user("hi")])
    memory.set_active_chat("c1")
    assert memory.get_active_chat() == "c1"


def test_active_falls_back_to_most_recent_chat(monkeypatch):
    times = iter([1.0, 2.0])
    monkeypatch.setattr(memory.time, "time", lambda: next(times))
    memory.save_chat("a", [user("a")])
    memory.save_chat("b", [user("b")])
    assert memory.get_active_chat() == "b"


def test_cli_api_uses_active_chat_and_new_keeps_old():
    memory.save_memory([user("one")])
    first = memory.get_active_chat()
    assert memory.load_memory()[0]["content"] == "one"
    memory.clear_memory()                 # CLI --new
    assert memory.get_active_chat() != first and memory.load_memory() == []
    assert memory.load_chat(first)[0]["content"] == "one"  # history kept


def test_legacy_session_file_is_migrated(chat_dir):
    (chat_dir / "session_state.json").write_text(json.dumps([user("old session")]))
    chats = memory.list_chats()
    assert [c["title"] for c in chats] == ["old session"]
    assert not os.path.exists(memory.LEGACY_FILE)
    assert memory.load_chat(chats[0]["id"])[0]["content"] == "old session"


def test_corrupt_chat_file_does_not_crash(chat_dir):
    memory.save_chat("bad", [user("x")])
    (chat_dir / "chats" / "bad.json").write_text("{not json")
    assert memory.load_chat("bad") == []
