
## LLM providers

The provider is selected with the `LLM_PROVIDER` variable in `.env` (template: `.env.example`):

| `LLM_PROVIDER` | Key in `.env` | Default model |
|---|---|---|
| `gemini` (default) | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| `openai` | `OPENAI_API_KEY` | `gpt-5-nano` |
| `azure` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | `gpt-4o-mini` (deployment name) |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4.1-mini` |
| `ollama` | none (local) | `gemma4:e4b` (`OLLAMA_CHAT`) |
| `proxy` | none ([teg-proxy](https://github.com/adrianstando/2026Z-PJATK-TEG/tree/main/tools/teg-proxy)) | `copilot/gpt-5-mini` |

`LLM_MODEL` overrides the provider's model. All providers except Anthropic use an OpenAI-compatible client, and Anthropic has an adapter in `llm_provider.py`, so the agent (`main.py`, `app.py`, `reviewer.py`) works the same way with each of them. In the Streamlit app the provider can be changed in the sidebar.

Tools are described with an OpenAI-format schema (`schema_<name>` as a plain dict). Session memory is saved as `agent_workspace/session_state.json`.

## Chats

Every conversation is saved in `agent_workspace/chats/` and listed in the Streamlit sidebar, where you can start a new chat, switch between chats, or delete one with 🗑️. A chat can be continued with a different provider. The CLI (`main.py`) continues the chat that is currently open in the app; `--new` starts a fresh chat and keeps the old one in the history.
