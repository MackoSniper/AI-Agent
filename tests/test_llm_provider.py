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


# === streaming ===

def _chunk(content=None, tool_calls=None, usage=None, no_choices=False):
    choices = [] if no_choices else [SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    return SimpleNamespace(choices=choices, usage=usage)


def _tc(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def _stream_client(chunks, seen=None):
    def create(**kwargs):
        if seen is not None:
            seen.append(kwargs)
        return iter(chunks)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _run_stream(chunks, **kwargs):
    events = list(lp.stream_complete([{"role": "user", "content": "hi"}], client=_stream_client(chunks), **kwargs))
    return [e[1] for e in events if e[0] == "text"], events[-1]


def test_stream_text_deltas_and_usage():
    usage = SimpleNamespace(prompt_tokens=5, completion_tokens=2)
    texts, done = _run_stream([_chunk("Hel"), _chunk("lo"), _chunk(no_choices=True, usage=usage)])
    assert texts == ["Hel", "lo"]
    assert done[0] == "done" and done[1] == {"role": "assistant", "content": "Hello"} and done[2] is usage


def test_stream_requests_streaming_with_usage():
    seen = []
    list(lp.stream_complete([{"role": "user", "content": "hi"}], client=_stream_client([_chunk("x")], seen)))
    assert seen[0]["stream"] is True and seen[0]["stream_options"] == {"include_usage": True}


def test_stream_retries_without_stream_options():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if "stream_options" in kwargs:
            raise RuntimeError("unsupported")
        return iter([_chunk("ok")])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    events = list(lp.stream_complete([{"role": "user", "content": "hi"}], client=client))
    assert events[-1][1]["content"] == "ok" and len(calls) == 2


def test_stream_tool_call_arguments_are_assembled():
    chunks = [
        _chunk(tool_calls=[_tc(0, id="a", name="f", arguments="")]),
        _chunk(tool_calls=[_tc(0, arguments='{"x"')]),
        _chunk(tool_calls=[_tc(0, arguments=": 1}")]),
        _chunk(tool_calls=[_tc(1, id="b", name="g", arguments="{}")]),
    ]
    _, done = _run_stream(chunks)
    calls = done[1]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["f", "g"]
    assert json.loads(calls[0]["function"]["arguments"]) == {"x": 1}
    assert done[1]["content"] is None


def test_stream_parallel_calls_sharing_index_zero():
    # Gemini's OpenAI-compatible endpoint sends every parallel call with index 0 and no id
    chunks = [
        _chunk(tool_calls=[_tc(0, name="f", arguments='{"a": 1}')]),
        _chunk(tool_calls=[_tc(0, name="g", arguments='{"b": 2}')]),
    ]
    _, done = _run_stream(chunks)
    calls = done[1]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["f", "g"]
    assert all(c["id"].startswith("call_") for c in calls) and calls[0]["id"] != calls[1]["id"]


def test_anthropic_stream_events_become_openai_chunks():
    E = SimpleNamespace
    events = [
        E(type="message_start", message=E(usage=E(input_tokens=7))),
        E(type="content_block_delta", index=0, delta=E(type="text_delta", text="Hi")),
        E(type="content_block_start", index=1, content_block=E(type="tool_use", id="t1", name="f")),
        E(type="content_block_delta", index=1, delta=E(type="input_json_delta", partial_json='{"q": ')),
        E(type="content_block_delta", index=1, delta=E(type="input_json_delta", partial_json='1}')),
        E(type="message_delta", usage=E(output_tokens=9)),
    ]

    class Ctx:
        def __enter__(self): return iter(events)
        def __exit__(self, *a): return False

    raw = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Ctx()))
    completions = lp._AnthropicCompletions(raw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    out = list(lp.stream_complete([{"role": "user", "content": "hi"}], client=client, provider="anthropic"))
    assert out[0] == ("text", "Hi")
    done = out[-1]
    assert done[1]["content"] == "Hi"
    assert done[1]["tool_calls"][0]["id"] == "t1"
    assert json.loads(done[1]["tool_calls"][0]["function"]["arguments"]) == {"q": 1}
    assert (done[2].prompt_tokens, done[2].completion_tokens) == (7, 9)
