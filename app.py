import streamlit as st # type: ignore[import]
import os
import json
from PIL import Image # type: ignore[import]
import io
import base64
from streamlit_mic_recorder import mic_recorder # type: ignore[import]


# Import our modules
from call_function import call_function, get_tools
from config import MAX_ITERS
from llm_provider import PROVIDERS, complete, describe, get_client, get_model, get_provider, message_to_dict, missing_env
from prompts import system_prompt
from reviewer import review_code
from memory import load_memory, save_memory, clear_memory

# Page configuration
st.set_page_config(page_title="AI Agent Workspace", page_icon="🤖", layout="wide")

# Sensitive functions that require approval
SENSITIVE_FUNCTIONS = ["write_file", "run_python_file"]

# === STATE INITIALIZATION (SESSION STATE) ===
if "messages" not in st.session_state:
    st.session_state.messages = load_memory()  # Load memory from file on startup

if "agent" not in st.session_state:
    st.session_state.agent = None  # state of the running agent loop (see run_agent)

if "provider" not in st.session_state:
    st.session_state.provider = get_provider()  # default from LLM_PROVIDER in .env

# === UI: SIDEBAR ===
with st.sidebar:
    st.title("🔧 Control Panel")
    if st.button("🧹 Clear memory"):
        clear_memory()
        st.session_state.messages = []
        st.session_state.agent = None
        st.rerun()
    
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
    st.success("✅ Docker Sandbox")

    # --- AGENT'S EYES ---
    st.markdown("---")
    st.subheader("📸 Agent's Eyes")
    uploaded_file = st.file_uploader(
        "Show an image (Screenshot/Photo)", 
        type=["png", "jpg", "jpeg", "webp"],
        key="vision_input"
    )
    
    image_input = None
    if uploaded_file:
        image_input = Image.open(uploaded_file)
        st.image(image_input, caption="Image to send", width=True)

    
    # --- AUDIO SERVICE (MICROPHONE) ---
    st.markdown("---")
    st.subheader("🎤 Agent's Ears")

    # Recording component
    audio_input = mic_recorder(
        start_prompt="🔴 Record",
        stop_prompt="⏹️ Stop",
        just_once=True,
        key='recorder'
    )

# === UI: MAIN CHAT WINDOW ===
st.title("🤖 AI Super-Agent")
st.caption(f"Powered by {describe(st.session_state.provider)} & Python")

def _message_text(content):
    """Text of a message: a plain string or a list of parts (text/image/audio)."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if p.get("type") == "text")


# Display the chat history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(_message_text(msg["content"]))
            # Images and recordings from previous turns are skipped for readability.

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
                    response = complete(
                        state["messages"],
                        system=system_prompt,
                        tools=get_tools(),
                        client=get_client(st.session_state.provider),
                        provider=st.session_state.provider,
                    )
                    state["iter"] += 1
                    assistant_message = message_to_dict(response.choices[0].message)
                    state["messages"].append(assistant_message)

                    # No tool calls = the agent is done
                    if not assistant_message.get("tool_calls"):
                        status.update(label="Done!", state="complete", expanded=False)
                        message_placeholder.markdown(assistant_message["content"] or "")
                        st.session_state.messages = state["messages"]
                        save_memory(st.session_state.messages)
                        st.session_state.agent = None
                        return

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


# 1. Get the text input (locked while the agent is waiting for approval)
_agent = st.session_state.agent
prompt_text = st.chat_input("What would you like to ask?", disabled=bool(_agent and _agent["awaiting"]))

# 2. Check what the user did (Typed or Recorded?)
user_action = None

if prompt_text:
    user_action = "text"
elif audio_input and not (_agent and _agent["awaiting"]):
    user_action = "audio"

# If there is any action (Text or Audio)
if user_action:
    user_parts = []  # message parts in OpenAI format
    
    # --- SCENARIO A: TEXT ---
    if user_action == "text":
        user_parts.append({"type": "text", "text": prompt_text})
        # Show in the chat
        with st.chat_message("user"):
            st.markdown(prompt_text)

    # --- SCENARIO B: AUDIO (VOICE) ---
    elif user_action == "audio":
        # Extract the bytes from the recording
        audio_bytes = audio_input['bytes']
        
        # Add the audio file for the model
        # (supported by e.g. Gemini and OpenAI audio models; other providers will ignore the recording)
        user_parts.append({"type": "input_audio", "input_audio": {"data": base64.b64encode(audio_bytes).decode(), "format": "wav"}})
        # Add a helper instruction
        user_parts.append({"type": "text", "text": "Listen to this recording and carry out the instruction."})
        
        # Show the player in the chat (so you can see it worked)
        with st.chat_message("user"):
            st.audio(audio_bytes, format="audio/wav")
            st.caption("🎙️ Voice message")

    # --- COMMON: IMAGE (If added in the sidebar) ---
    if image_input:
        img_byte_arr = io.BytesIO()
        image_input.save(img_byte_arr, format=image_input.format)
        img_bytes = img_byte_arr.getvalue()
        
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_input.format.lower()};base64,{base64.b64encode(img_bytes).decode()}"},
        })
        # Show the image in the chat
        with st.chat_message("user"):
            st.image(image_input, width=200)

    # 3. Save in the history
    st.session_state.messages.append({"role": "user", "content": user_parts})

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

if st.session_state.agent:
    run_agent()
