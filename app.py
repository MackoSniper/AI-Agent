import streamlit as st # type: ignore[import]
import os
import json
import base64


# Import our modules
from call_function import call_function, get_tools
from config import MAX_ITERS, SENSITIVE_FUNCTIONS
from llm_provider import PROVIDERS, describe, get_client, get_model, get_provider, missing_env, stream_complete
from prompts import system_prompt
from reviewer import review_code
from memory import delete_chat, get_active_chat, list_chats, load_chat, new_chat_id, save_chat, set_active_chat

# Page configuration
st.set_page_config(page_title="AI Agent Workspace", page_icon="🤖", layout="wide")

# === STATE INITIALIZATION (SESSION STATE) ===
if "chat_id" not in st.session_state:
    st.session_state.chat_id = get_active_chat()  # the chat that was open last (shared with the CLI)

if "messages" not in st.session_state:
    st.session_state.messages = load_chat(st.session_state.chat_id)

if "agent" not in st.session_state:
    st.session_state.agent = None  # state of the running agent loop (see run_agent)

if "provider" not in st.session_state:
    st.session_state.provider = get_provider()  # default from LLM_PROVIDER in .env

# === CHATS: switching, creating, deleting ===

def _open_chat(chat_id):
    """Makes `chat_id` the current chat and loads its history."""
    st.session_state.chat_id = chat_id
    st.session_state.messages = load_chat(chat_id)
    st.session_state.agent = None  # drop any unfinished agent turn of the previous chat
    set_active_chat(chat_id)


def _new_chat():
    # Nothing is saved until the first message, so empty chats never pile up in the list.
    _open_chat(new_chat_id())


def _delete_chat(chat_id):
    delete_chat(chat_id)
    if chat_id == st.session_state.chat_id:
        remaining = list_chats()
        _open_chat(remaining[0]["id"] if remaining else new_chat_id())


# === UI: SIDEBAR ===
# The delete buttons are icon-only: drop the label gap/padding so the icon sits exactly in the middle.
st.markdown(
    """
    <style>
    [class*="st-key-del_"] button { padding: 0; justify-content: center; }
    [class*="st-key-del_"] button > div,
    [class*="st-key-del_"] button p { margin: 0; width: 100%; display: flex; justify-content: center; }
    </style>
    """,
    unsafe_allow_html=True,
)
with st.sidebar:
    st.title("🔧 Control Panel")

    # --- CHAT HISTORY ---
    busy = bool(st.session_state.agent and st.session_state.agent["awaiting"])  # no switching mid-approval
    st.button("➕ New chat", width="stretch", disabled=busy, on_click=_new_chat)
    chats = list_chats()
    if not any(c["id"] == st.session_state.chat_id for c in chats):
        st.button("💬 New chat", key="current_unsaved", width="stretch", type="primary", disabled=True)
    for chat in chats:
        is_current = chat["id"] == st.session_state.chat_id
        col_open, col_del = st.columns([5, 1], vertical_alignment="center")
        col_open.button(
            chat["title"],
            key=f"open_{chat['id']}",
            width="stretch",
            type="primary" if is_current else "secondary",
            disabled=busy,
            on_click=_open_chat,
            args=(chat["id"],),
        )
        col_del.button(":material/delete:", key=f"del_{chat['id']}", help="Delete this chat", width="stretch",
                       disabled=busy, on_click=_delete_chat, args=(chat["id"],))

    st.markdown("---")
    st.subheader("🧠 Model")
    st.session_state.provider = st.selectbox(
        "LLM provider",
        PROVIDERS,
        index=PROVIDERS.index(st.session_state.provider),
    )
    st.caption(f"Model: `{get_model(st.session_state.provider)}`")
    missing = missing_env(st.session_state.provider)
    if missing:
        st.error(f"Missing in .env: {', '.join(missing)}")

    st.markdown("---")
    st.markdown("**Active modules:**")
    st.success("✅ Dynamic Loader")
    st.success("✅ Code Reviewer")
    st.success("✅ Long-term Memory")
    st.success("✅ Internet Access")

# === UI: MAIN CHAT WINDOW ===
st.title("🤖 AI Super-Agent")
st.caption(f"Powered by {describe(st.session_state.provider)} & Python")

def _render_user_content(content):
    """Shows a user message: text plus any attached images / voice recordings."""
    if isinstance(content, str):
        st.markdown(content)
        return
    for part in content or []:
        if part.get("type") == "text":
            st.markdown(part["text"])
        elif part.get("type") == "image_url":
            st.image(base64.b64decode(part["image_url"]["url"].split(",", 1)[1]), width=200)
        elif part.get("type") == "input_audio":
            st.audio(base64.b64decode(part["input_audio"]["data"]), format="audio/wav")


# Display the chat history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            _render_user_content(msg["content"])

    elif msg["role"] == "assistant":
        if msg.get("content"):
            with st.chat_message("assistant"):
                st.markdown(msg["content"])

    # === Display charts created by the Agent ===
    elif msg["role"] == "tool":
        # Check whether the tool returned information about a created image file
        resp = str(msg["content"])
        # Simple heuristic: if the response contains ".png" or ".jpg"
        if ".png" in resp or ".jpg" in resp:
            import glob
            # Look for the newest file in the workspace
            files = glob.glob("agent_workspace/*.png") + glob.glob("agent_workspace/*.jpg")
            if files:
                latest_file = max(files, key=os.path.getmtime)
                with st.chat_message("assistant"):
                    st.image(latest_file, caption="Generated file", width=400)

# === AGENT LOGIC ===
# Streamlit re-runs the whole script after every click, so the agent loop is resumable:
# its state (history, tool-call queue, pending approval) is kept in st.session_state.agent.
# When a sensitive action needs approval, the loop shows buttons and ends the current re-run;
# the click sets the decision and the script resumes the loop at exactly that point.

def _tool_error(call, message):
    return {"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"error": message}, ensure_ascii=False)}


def _decide(decision):
    st.session_state.agent["decision"] = decision


def _approval_card(call, name, args):
    """Card with Approve / Deny buttons for a sensitive action."""
    st.warning(f"⚠️ Agent wants to execute: **{name}**")
    if name == "write_file":
        st.caption(f"File: `{args.get('file_path', '')}`")
        st.code(args.get("content", ""), language="python" if args.get("file_path", "").endswith(".py") else None)
    elif name == "run_python_file":
        st.caption(f"File: `{args.get('file_path', '')}`  |  arguments: `{args.get('args') or []}`")
    elif name == "install_package":
        st.caption(f"Package: `{args.get('package_name', '')}` (installed with pip into this project's environment)")
    else:
        st.json(args)
    col_ok, col_no, _ = st.columns([1, 1, 4])
    col_ok.button("✅ Approve", key=f"ok_{call['id']}", type="primary", on_click=_decide, args=("approve",))
    col_no.button("❌ Deny", key=f"no_{call['id']}", on_click=_decide, args=("deny",))


def _process_call(call, state, status):
    """Handles a single tool call. Returns a 'tool' role message, or None when waiting for approval."""
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}

    status.write(f"🛠️ Agent wants to use: `{name}`")

    # --- REVIEWER (once per call, result remembered while waiting for approval) ---
    if name == "write_file" and args.get("file_path", "").endswith(".py"):
        if call["id"] not in state["reviews"]:
            status.info(f"🔍 Reviewer is checking the code: {args['file_path']}")
            state["reviews"][call["id"]] = review_code(args.get("content", ""))
        is_approved, feedback = state["reviews"][call["id"]]
        if not is_approved:
            status.error(f"❌ Reviewer rejected the code: {feedback}")
            return _tool_error(call, f"Security Review Failed: {feedback}. Please fix the code and try again.")
        status.success("✅ Reviewer approved the code.")

    # --- USER APPROVAL ---
    if name in SENSITIVE_FUNCTIONS:
        verdict = state["decided"].get(call["id"])
        if verdict is None:
            if state["awaiting"] != call["id"]:
                state["awaiting"] = call["id"]
                st.rerun()  # re-run so the chat box is locked while approval is pending
            if state["decision"] is None:
                status.update(label="Waiting for your approval...", state="running", expanded=True)
                _approval_card(call, name, args)
                return None
            state["decided"][call["id"]] = state["decision"]
            state["awaiting"], state["decision"] = None, None
            st.rerun()  # resume with the chat box unlocked
        if verdict == "deny":
            status.write(f"❌ Denied: `{name}`")
            return _tool_error(call, "User denied execution of this function.")
        status.write(f"✅ Approved: `{name}`")

    result = call_function(call, verbose=True)
    status.code(f"Wynik: {result['content'][:200]}...")
    return result


def run_agent():
    """Starts or resumes the agent loop. Ends when the agent answers or is waiting for approval."""
    state = st.session_state.agent
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        status = st.status("Thinking...", expanded=True)
        try:
            while state["iter"] < MAX_ITERS:
                if state["calls"] is None:
                    status.write(f"🔄 Iteration {state['iter'] + 1}...")
                    # Stream the answer into the placeholder as it arrives (▌ = cursor)
                    text, assistant_message = "", None
                    for event in stream_complete(
                        state["messages"],
                        system=system_prompt,
                        tools=get_tools(),
                        client=get_client(st.session_state.provider),
                        provider=st.session_state.provider,
                    ):
                        if event[0] == "text":
                            text += event[1]
                            message_placeholder.markdown(text + "▌")
                        else:
                            assistant_message = event[1]
                    state["iter"] += 1
                    state["messages"].append(assistant_message)

                    # No tool calls = the agent is done
                    if not assistant_message.get("tool_calls"):
                        status.update(label="Done!", state="complete", expanded=False)
                        message_placeholder.markdown(assistant_message["content"] or "")  # final text, no cursor
                        st.session_state.messages = state["messages"]
                        save_chat(st.session_state.chat_id, st.session_state.messages)
                        st.session_state.agent = None
                        return

                    # Text that came before tool calls ("Let me check...") goes into the status log,
                    # so the placeholder is free for the next streamed answer.
                    if assistant_message.get("content"):
                        status.write(assistant_message["content"])
                    message_placeholder.empty()

                    state["calls"], state["idx"], state["tool_messages"] = assistant_message["tool_calls"], 0, []

                while state["idx"] < len(state["calls"]):
                    outcome = _process_call(state["calls"][state["idx"]], state, status)
                    if outcome is None:
                        return  # waiting for a click; the script will resume the loop after the re-run
                    state["tool_messages"].append(outcome)
                    state["idx"] += 1

                state["messages"].extend(state["tool_messages"])
                state["calls"] = None

            status.update(label="Iteration limit", state="error")
            st.error(f"Maximum number of iterations reached ({MAX_ITERS}).")
            st.session_state.agent = None
        except Exception as e:
            st.session_state.agent = None
            st.error(f"Critical error: {e}")


# 1. Chat input with the standard attach (📎) and microphone (🎤) buttons built into the bar.
#    Locked while the agent is waiting for approval.
_agent = st.session_state.agent
submission = st.chat_input(
    "What would you like to ask?",
    accept_file="multiple",
    file_type=["png", "jpg", "jpeg", "webp"],
    accept_audio=True,
    disabled=bool(_agent and _agent["awaiting"]),
)

# 2. If the user sent anything (text, images, a voice recording)
if submission:
    text = (submission.get("text") or "").strip()
    images = submission.get("files") or []
    audio = submission.get("audio")

    user_parts = []  # message parts in OpenAI format
    if text:
        user_parts.append({"type": "text", "text": text})

    for image in images:
        mime = image.type or "image/png"
        data = base64.b64encode(image.getvalue()).decode()
        user_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})

    if audio:
        # (supported by e.g. Gemini and OpenAI audio models; other providers will ignore the recording)
        data = base64.b64encode(audio.getvalue()).decode()
        user_parts.append({"type": "input_audio", "input_audio": {"data": data, "format": "wav"}})

    if not text:  # nothing typed: tell the model what to do with the attachment
        user_parts.append({"type": "text", "text": "Listen to this recording and carry out the instruction." if audio
                           else "Look at the attached image(s) and describe them."})

    # 3. Save in the history
    st.session_state.messages.append({"role": "user", "content": user_parts})
    save_chat(st.session_state.chat_id, st.session_state.messages)  # saved right away: it names the chat in the list

    # 4. Run the Agent
    st.session_state.agent = {
        "messages": st.session_state.messages.copy(),
        "iter": 0,
        "calls": None,         # queue of tool calls from the model's last response
        "idx": 0,              # which call is being handled
        "tool_messages": [],
        "reviews": {},         # Reviewer results by call id
        "awaiting": None,      # id of the call waiting for approval
        "decision": None,      # user click: "approve" / "deny"
        "decided": {},         # remembered decisions by call id
    }
    st.rerun()  # redraw so the sidebar (chat list) and the history already include this message

if st.session_state.agent:
    run_agent()
