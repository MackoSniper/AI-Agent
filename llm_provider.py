"""Warstwa dostawców LLM.

Wzorowane na repozytorium kursu 2026Z-PJATK-TEG: dostawcę wybiera się zmienną LLM_PROVIDER w .env.
Wszyscy dostawcy poza Anthropic mówią protokołem zgodnym z OpenAI (zmienia się tylko base_url, klucz
i nazwa modelu). Anthropic ma własny, cienki adapter, który wystawia ten sam interfejs
`client.chat.completions.create(...)`, więc reszta kodu nie wie, z kim rozmawia.

Format wiadomości w całym projekcie to format OpenAI:
    {"role": "user" | "assistant" | "tool", "content": ..., "tool_calls": [...], "tool_call_id": ...}
"""
import json
import os
import uuid
from types import SimpleNamespace

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

DEFAULT_PROVIDER = "gemini"

# Model używany przez agenta dla każdego dostawcy. Nadpisanie: LLM_MODEL w .env.
# Dla Azure to nazwa deploymentu, dla Ollamy nazwa pobranego modelu.
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

# Zmienne środowiskowe wymagane przez dostawcę.
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

# Dostawcy, którzy akceptują parametr temperature (modele gpt-5 i nowe Claude go odrzucają).
SUPPORTS_TEMPERATURE = {"gemini", "deepseek", "ollama", "openrouter"}


def get_provider(provider=None):
    """Zwraca nazwę dostawcy: argument, potem LLM_PROVIDER z .env, potem domyślny."""
    name = (provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if name not in MODELS:
        raise RuntimeError(f"Unknown LLM_PROVIDER '{name}'. Available: {', '.join(PROVIDERS)}")
    return name


def get_model(provider=None):
    return os.getenv("LLM_MODEL") or MODELS[get_provider(provider)]


def missing_env(provider=None):
    """Lista brakujących zmiennych środowiskowych dla dostawcy (pusta = wszystko jest)."""
    return [k for k in REQUIRED_ENV[get_provider(provider)] if not os.environ.get(k)]


def describe(provider=None):
    return f"{get_provider(provider)} ({get_model(provider)})"


# === ADAPTER ANTHROPIC =====================================================

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
        else:  # np. input_audio: Anthropic nie obsługuje audio
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
                last["content"].append(block)  # wyniki równoległych wywołań trafiają do jednej wiadomości
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

    def create(self, model, messages, tools=None, max_tokens=8192, **_ignored):
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
        return _from_anthropic(self._client.messages.create(**kwargs))


class AnthropicClient:
    """Udaje klienta OpenAI: `client.chat.completions.create(...)`."""

    def __init__(self):
        import anthropic  # type: ignore[import]  # import leniwy: pakiet potrzebny tylko dla tego dostawcy
        self.chat = SimpleNamespace(completions=_AnthropicCompletions(anthropic.Anthropic()))


# === KLIENT ================================================================

def get_client(provider=None):
    """Tworzy klienta dla dostawcy. Rzuca RuntimeError z czytelnym komunikatem, gdy brakuje konfiguracji."""
    name = get_provider(provider)
    missing = missing_env(name)
    if missing:
        raise RuntimeError(f"Provider '{name}' requires environment variable(s): {', '.join(missing)}")

    if name == "anthropic":
        return AnthropicClient()

    from openai import AzureOpenAI, OpenAI  # type: ignore[import]

    if name == "azure":
        return AzureOpenAI(api_version="2024-12-01-preview")  # endpoint i klucz z .env
    if name == "openai":
        return OpenAI()
    if name == "gemini":
        return OpenAI(base_url=BASE_URLS[name], api_key=os.environ["GEMINI_API_KEY"])
    if name in ("deepseek", "openrouter"):
        return OpenAI(base_url=BASE_URLS[name], api_key=os.environ[REQUIRED_ENV[name][0]])
    if name == "ollama":
        return OpenAI(base_url=BASE_URLS[name], api_key="ollama")  # klucz wymagany, ale ignorowany
    return OpenAI(base_url=BASE_URLS[name], api_key="teg")  # proxy


def complete(messages, system=None, tools=None, temperature=None, client=None, provider=None):
    """Jedno wywołanie modelu. Zwraca odpowiedź w kształcie OpenAI (choices[0].message, usage)."""
    name = get_provider(provider)
    client = client or get_client(name)

    full = ([{"role": "system", "content": system}] if system else []) + list(messages)
    kwargs = {"model": get_model(name), "messages": full}
    if tools:
        kwargs["tools"] = tools
    if temperature is not None and name in SUPPORTS_TEMPERATURE:
        kwargs["temperature"] = temperature
    return client.chat.completions.create(**kwargs)


def message_to_dict(message):
    """Zamienia odpowiedź modelu na zwykły słownik (do historii, pamięci JSON i kolejnego wywołania)."""
    d = {"role": "assistant", "content": message.content}
    if getattr(message, "tool_calls", None):
        d["tool_calls"] = [{
            "id": tc.id or f"call_{uuid.uuid4().hex[:12]}",  # niektórzy dostawcy zwracają puste id
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
        } for tc in message.tool_calls]
    return d
