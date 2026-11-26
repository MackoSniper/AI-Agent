import json

import main
from config import SENSITIVE_FUNCTIONS


def test_install_package_needs_approval():
    assert {"write_file", "run_python_file", "install_package"} <= set(SENSITIVE_FUNCTIONS)


def _tool_call_turn(name, args):
    call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return iter([("done", {"role": "assistant", "content": None, "tool_calls": [call]}, None)])


def _run_cli_turn(monkeypatch, answer, ran):
    monkeypatch.setattr(main, "stream_complete", lambda *a, **k: _tool_call_turn("install_package", {"package_name": "left-pad"}))
    monkeypatch.setattr(main, "save_memory", lambda messages: None)
    monkeypatch.setattr(main, "call_function", lambda call, verbose=False: ran.append(call) or
                        {"role": "tool", "tool_call_id": call["id"], "content": '{"result": "installed"}'})
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    messages = [{"role": "user", "content": "install left-pad"}]
    main.generate_content(client=None, messages=messages, verbose=False)
    return messages[-1]


def test_cli_denied_install_is_not_executed(monkeypatch):
    ran = []
    result = _run_cli_turn(monkeypatch, "n", ran)
    assert ran == []
    assert "denied" in json.loads(result["content"])["error"].lower()


def test_cli_approved_install_is_executed(monkeypatch):
    ran = []
    result = _run_cli_turn(monkeypatch, "y", ran)
    assert len(ran) == 1 and ran[0]["function"]["name"] == "install_package"
    assert json.loads(result["content"]) == {"result": "installed"}
