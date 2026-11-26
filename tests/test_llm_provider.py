import json
from types import SimpleNamespace

import pytest

import llm_provider as lp


def test_default_provider_and_model(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert lp.get_provider() == "gemini"
    assert lp.get_model() == "gemini-2.5-flash"


def test_provider_from_env_and_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "DeepSeek")
    assert lp.get_provider() == "deepseek"
    monkeypatch.setenv("LLM_MODEL", "my-model")
    assert lp.get_model() == "my-model"


def test_unknown_provider_rejected():
    with pytest.raises(RuntimeError):
        lp.get_provider("nope")


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        lp.get_client("openai")


def test_ollama_needs_no_key():
    assert lp.missing_env("ollama") == []


def test_complete_builds_request(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return "resp"

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = lp.complete([{"role": "user", "content": "hi"}], system="sys", tools=[{"x": 1}], temperature=0.0,
                      client=client, provider="gemini")
    assert out == "resp"
    assert seen["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["tools"] == [{"x": 1}] and seen["temperature"] == 0.0


def test_temperature_omitted_for_openai(monkeypatch):
    seen = {}
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: seen.update(k))))
    lp.complete([{"role": "user", "content": "hi"}], temperature=0.0, client=client, provider="openai")
    assert "temperature" not in seen and "tools" not in seen


def test_message_to_dict_fills_missing_tool_call_id():
    msg = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id="", function=SimpleNamespace(name="f", arguments=None))])
    d = lp.message_to_dict(msg)
    assert d["tool_calls"][0]["id"].startswith("call_")
    assert d["tool_calls"][0]["function"]["arguments"] == "{}"


def test_anthropic_message_conversion():
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": [{"type": "text", "text": "hi"},
                                     {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "a", "arguments": '{"x": 1}'}},
            {"id": "t2", "type": "function", "function": {"name": "b", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "r1"},
        {"role": "tool", "tool_call_id": "t2", "content": "r2"},
    ]
    system, out = lp._to_anthropic(messages)
    assert system == "be brief"
    assert out[0]["content"][1]["source"] == {"type": "base64", "media_type": "image/png", "data": "AAAA"}
    assert out[1]["content"][0] == {"type": "tool_use", "id": "t1", "name": "a", "input": {"x": 1}}
    assert len(out) == 3 and [b["tool_use_id"] for b in out[2]["content"]] == ["t1", "t2"]


def test_anthropic_response_conversion():
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok"),
                 SimpleNamespace(type="tool_use", id="t1", name="a", input={"q": "z"})],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
    )
    msg = lp._from_anthropic(resp).choices[0].message
    assert msg.content == "ok"
    assert msg.tool_calls[0].function.name == "a"
    assert json.loads(msg.tool_calls[0].function.arguments) == {"q": "z"}
