
## Dostawcy LLM

Dostawcę wybiera się zmienną `LLM_PROVIDER` w pliku `.env` (szablon: `.env.example`):

| `LLM_PROVIDER` | Klucz w `.env` | Domyślny model |
|---|---|---|
| `gemini` (domyślny) | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| `openai` | `OPENAI_API_KEY` | `gpt-5-nano` |
| `azure` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | `gpt-4o-mini` (nazwa deploymentu) |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4.1-mini` |
| `ollama` | brak (lokalnie) | `gemma4:e4b` (`OLLAMA_CHAT`) |
| `proxy` | brak ([teg-proxy](https://github.com/adrianstando/2026Z-PJATK-TEG/tree/main/tools/teg-proxy)) | `copilot/gpt-5-mini` |

`LLM_MODEL` nadpisuje model dostawcy. Wszyscy dostawcy poza Anthropic korzystają z klienta zgodnego z OpenAI, a Anthropic ma adapter w `llm_provider.py`, więc agent (`main.py`, `app.py`, `reviewer.py`) działa tak samo z każdym z nich. W aplikacji Streamlit dostawcę można zmienić w panelu bocznym.

Narzędzia opisuje się schematem w formacie OpenAI (`schema_<nazwa>` jako zwykły słownik). Pamięć sesji jest zapisywana jako `agent_workspace/session_state.json`.
