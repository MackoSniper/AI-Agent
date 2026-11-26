"""LLM provider layer.

Modeled on the course repository 2026Z-PJATK-TEG: the provider is selected with the LLM_PROVIDER variable in .env.
All providers except Anthropic speak an OpenAI-compatible protocol (only base_url, the key
and the model name change). Anthropic has its own thin adapter that exposes the same interface
`client.chat.completions.create(...)`, so the rest of the code does not know who it is talking to.

The message format throughout the project is the OpenAI format:
    {"role": "user" | "assistant" | "tool", "content": ..., "tool_calls": [...], "tool_call_id": ...}
"""
import json
import os
import uuid
from types import SimpleNamespace

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

DEFAULT_PROVIDER = "gemini"

# Model used by the agent for each provider. Override: LLM_MODEL in .env.
# For Azure this is the deployment name, for Ollama the name of the pulled model.
MODELS = {
    "gemini":     "gemini-2.5-flash",
    "openai":     "gpt-5-nano",
    "azure":      "gpt-4o-mini",
    "anthropic":  "claude-sonnet-5-5",
    "deepseek":   "deepseek-chat",
    "openrouter": "openai/gpt-4.1-mini",
    "ollama":     os.getenv("OLLAMA_CHAT", "gemma4:e4b"),
    "proxy":      "copilot/gpt-5-mini",
}

PROVIDERS = list(MODELS)

# Environment variables required by the provider.
REQUIRED_ENV = {
    "gemini":     ["GEMINI_API_KEY"],
    "openai":     ["OPENAI_API_KEY"],
    "azure":      ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"],
    "anthropic":  ["ANTHROPIC_API_KEY"],
    "deepseek":   ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "ollama":     [],
    "proxy":      [],
}

BASE_URLS = {
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "deepseek":   "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama":     "http://localhost:11434/v1",
    "proxy":      "http://localhost:8787/v1",
}

# Providers that accept the temperature parameter (gpt-5 models and new Claude models reject it).
SUPPORTS_TEMPERATURE = {"gemini", "deepseek", "ollama", "openrouter"}


def get_provider(provider=None):
    """Returns the provider name: the argument, then LLM_PROVIDER from .env, then the default."""
    name = (provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if name not in MODELS:
        raise RuntimeError(f"Unknown LLM_PROVIDER '{name}'. Available: {', '.join(PROVIDERS)}")
    return name


def get_model(provider=None):
    return os.getenv("LLM_MODEL") or MODELS[get_provider(provider)]


def missing_env(provider=None):
    """List of missing environment variables for the provider (empty = all present)."""
    return [k for k in REQUIRED_ENV[get_provider(provider)] if not os.environ.get(k)]


def describe(provider=None):
    return f"{get_provider(provider)} ({get_model(provider)})"


# === ANTHROPIC ADAPTER =====================================================

def _split_data_url(url):
    header, _, data = url.partition(",")
    media_type = header[len("data:"):].split(";")[0] or "image/png"
    return media_type, data


def _user_parts_to_anthropic(content):
    if isinstance(content, str):
        return content
    blocks = []
    for part in content or []:
        ptype = part.get("type")
        if ptype == "text":
            blocks.append({"type": "text", "text": part["text"]})
        elif ptype == "image_url":
            url = part["image_url"]["url"]
            if url.startswith("data:"):
                media_type, data = _split_data_url(url)
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
            else:
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
        else:  # e.g. input_audio: Anthropic does not support audio
            blocks.append({"type": "text", "text": f"[{ptype} omitted: not supported by Anthropic]"})
    return blocks


def _to_anthropic(messages):
    system_parts, out = [], []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
        elif role == "user":
            out.append({"role": "user", "content": _user_parts_to_anthropic(m["content"])})
        elif role == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"].get("arguments") or "{}"),
                })
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": str(m["content"])}
            last = out[-1] if out else None
            if last and last["role"] == "user" and isinstance(last["content"], list) \
                    and last["content"] and last["content"][-1].get("type") == "tool_result":
                last["content"].append(block)  # results of parallel calls go into a single message
            else:
                out.append({"role": "user", "content": [block]})
    return "\n\n".join(system_parts), out


def _from_anthropic(resp):
    text = "".join(b.text for b in resp.content if b.type == "text")
    tool_calls = [
        SimpleNamespace(id=b.id, type="function",
                        function=SimpleNamespace(name=b.name, arguments=json.dumps(b.input)))
        for b in resp.content if b.type == "tool_use"
    ]
    message = SimpleNamespace(role="assistant", content=text or None, tool_calls=tool_calls or None)
    usage = SimpleNamespace(prompt_tokens=resp.usage.input_tokens, completion_tokens=resp.usage.output_tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class _AnthropicCompletions:
    def __init__(self, client):
        self._client = client

    def create(self, model, messages, tools=None, max_tokens=8192, stream=False, **_ignored):
        system, converted = _to_anthropic(messages)
        kwargs = {"model": model, "max_tokens": max_tokens, "messages": converted}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [{
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}},
            } for t in tools]
        if stream:
            return self._stream(kwargs)
        return _from_anthropic(self._client.messages.create(**kwargs))

    def _stream(self, kwargs):
        """Translates Anthropic stream events into OpenAI-style chunks (delta.content / delta.tool_calls)."""
        def chunk(delta=None, usage=None):
            choices = [SimpleNamespace(delta=delta)] if delta is not None else []
            return SimpleNamespace(choices=choices, usage=usage)

        tool_slots = {}  # Anthropic content-block index -> OpenAI tool_call index
        input_tokens = 0
        with self._client.messages.stream(**kwargs) as events:
            for event in events:
                etype = event.type
                if etype == "message_start":
                    input_tokens = event.message.usage.input_tokens
                elif etype == "content_block_start" and event.content_block.type == "tool_use":
                    tool_slots[event.index] = len(tool_slots)
                    block = event.content_block
                    call = SimpleNamespace(index=tool_slots[event.index], id=block.id,
                                           function=SimpleNamespace(name=block.name, arguments=""))
                    yield chunk(SimpleNamespace(content=None, tool_calls=[call]))
                elif etype == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield chunk(SimpleNamespace(content=event.delta.text, tool_calls=None))
                    elif event.delta.type == "input_json_delta":
                        call = SimpleNamespace(index=tool_slots[event.index], id=None,
                                               function=SimpleNamespace(name=None, arguments=event.delta.partial_json))
                        yield chunk(SimpleNamespace(content=None, tool_calls=[call]))
                elif etype == "message_delta":
                    yield chunk(usage=SimpleNamespace(prompt_tokens=input_tokens,
                                                      completion_tokens=event.usage.output_tokens))


class AnthropicClient:
    """Pretends to be an OpenAI client: `client.chat.completions.create(...)`."""

    def __init__(self):
        import anthropic  # type: ignore[import]  # lazy import: the package is only needed for this provider
        self.chat = SimpleNamespace(completions=_AnthropicCompletions(anthropic.Anthropic()))


# === CLIENT ================================================================

def get_client(provider=None):
    """Creates a client for the provider. Raises RuntimeError with a clear message when configuration is missing."""
    name = get_provider(provider)
    missing = missing_env(name)
    if missing:
        raise RuntimeError(f"Provider '{name}' requires environment variable(s): {', '.join(missing)}")

    if name == "anthropic":
        return AnthropicClient()

    from openai import AzureOpenAI, OpenAI  # type: ignore[import]

    if name == "azure":
        return AzureOpenAI(api_version="2024-12-01-preview")  # endpoint and key from .env
    if name == "openai":
        return OpenAI()
    if name == "gemini":
        return OpenAI(base_url=BASE_URLS[name], api_key=os.environ["GEMINI_API_KEY"])
    if name in ("deepseek", "openrouter"):
        return OpenAI(base_url=BASE_URLS[name], api_key=os.environ[REQUIRED_ENV[name][0]])
    if name == "ollama":
        return OpenAI(base_url=BASE_URLS[name], api_key="ollama")  # key required but ignored
    return OpenAI(base_url=BASE_URLS[name], api_key="teg")  # proxy


def _build_request(messages, system, tools, temperature, name):
    full = ([{"role": "system", "content": system}] if system else []) + list(messages)
    kwargs = {"model": get_model(name), "messages": full}
    if tools:
        kwargs["tools"] = tools
    if temperature is not None and name in SUPPORTS_TEMPERATURE:
        kwargs["temperature"] = temperature
    return kwargs


def complete(messages, system=None, tools=None, temperature=None, client=None, provider=None):
    """A single model call. Returns a response in the OpenAI shape (choices[0].message, usage)."""
    name = get_provider(provider)
    client = client or get_client(name)
    return client.chat.completions.create(**_build_request(messages, system, tools, temperature, name))


def _open_stream(client, kwargs):
    # Ask for token usage in the last chunk; a few servers reject the option, so retry without it.
    try:
        return client.chat.completions.create(stream=True, stream_options={"include_usage": True}, **kwargs)
    except Exception:
        return client.chat.completions.create(stream=True, **kwargs)


def stream_complete(messages, system=None, tools=None, temperature=None, client=None, provider=None):
    """Streaming model call. A generator that yields:
        ("text", delta)             for every piece of text as it arrives
        ("done", message, usage)    once, at the end: `message` is the assistant dict (same as
                                    message_to_dict) and `usage` has prompt_tokens/completion_tokens or is None
    """
    name = get_provider(provider)
    client = client or get_client(name)
    stream = _open_stream(client, _build_request(messages, system, tools, temperature, name))

    text_parts, calls, usage = [], [], None
    last_for_index = {}  # tool_call index -> position in `calls`
    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if getattr(delta, "content", None):
            text_parts.append(delta.content)
            yield ("text", delta.content)
        for tc in getattr(delta, "tool_calls", None) or []:
            fn = tc.function
            idx = tc.index if tc.index is not None else 0
            # A chunk carrying a function name starts a new call. (Some providers, e.g. Gemini's compatible
            # endpoint, reuse index 0 for every parallel call, so the index alone is not enough.)
            if (fn and fn.name) or idx not in last_for_index:
                calls.append({"id": tc.id or "", "name": (fn.name if fn else "") or "", "arguments": ""})
                last_for_index[idx] = len(calls) - 1
            current = calls[last_for_index[idx]]
            if tc.id and not current["id"]:
                current["id"] = tc.id
            if fn and fn.arguments:
                current["arguments"] += fn.arguments

    message = {"role": "assistant", "content": "".join(text_parts) or None}
    if calls:
        message["tool_calls"] = [{
            "id": c["id"] or f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"},
        } for c in calls]
    yield ("done", message, usage)


def message_to_dict(message):
    """Converts a model response into a plain dict (for the history, JSON memory and the next call)."""
    d = {"role": "assistant", "content": message.content}
    if getattr(message, "tool_calls", None):
        d["tool_calls"] = [{
            "id": tc.id or f"call_{uuid.uuid4().hex[:12]}",  # some providers return an empty id
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
        } for tc in message.tool_calls]
    return d
