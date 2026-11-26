import streamlit as st # type: ignore[import]
import os
import json
import time
from PIL import Image # type: ignore[import]
import io
import base64
from streamlit_mic_recorder import mic_recorder # type: ignore[import]


# Importujemy nasze moduły
from call_function import call_function, get_tools
from llm_provider import PROVIDERS, complete, describe, get_client, get_model, get_provider, message_to_dict, missing_env
from prompts import system_prompt
from reviewer import review_code
from memory import load_memory, save_memory, clear_memory

# Konfiguracja strony
st.set_page_config(page_title="AI Agent Workspace", page_icon="🤖", layout="wide")

# Funkcje wrażliwe wymagające zgody
SENSITIVE_FUNCTIONS = ["write_file", "run_python_file"]

# === INICJALIZACJA STANU (SESSION STATE) ===
if "messages" not in st.session_state:
    st.session_state.messages = load_memory()  # Ładujemy pamięć z pliku na start

if "provider" not in st.session_state:
    st.session_state.provider = get_provider()  # domyślnie z LLM_PROVIDER w .env

# === UI: PASEK BOCZNY ===
with st.sidebar:
    st.title("🔧 Panel Sterowania")
    if st.button("🧹 Wyczyść pamięć"):
        clear_memory()
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    st.subheader("🧠 Model")
    st.session_state.provider = st.selectbox(
        "Dostawca LLM",
        PROVIDERS,
        index=PROVIDERS.index(st.session_state.provider),
    )
    st.caption(f"Model: `{get_model(st.session_state.provider)}`")
    missing = missing_env(st.session_state.provider)
    if missing:
        st.error(f"Brak w .env: {', '.join(missing)}")

    st.markdown("---")
    st.markdown("**Aktywne moduły:**")
    st.success("✅ Dynamic Loader")
    st.success("✅ Code Reviewer")
    st.success("✅ Long-term Memory")
    st.success("✅ Internet Access")
    st.success("✅ Docker Sandbox")

    # --- OCZY AGENTA ---
    st.markdown("---")
    st.subheader("📸 Oczy Agenta")
    uploaded_file = st.file_uploader(
        "Pokaż obraz (Screenshot/Foto)", 
        type=["png", "jpg", "jpeg", "webp"],
        key="vision_input"
    )
    
    image_input = None
    if uploaded_file:
        image_input = Image.open(uploaded_file)
        st.image(image_input, caption="Obraz do wysłania", width=True)

    
    # --- USŁUGA AUDIO (MIKROFON) ---
    st.markdown("---")
    st.subheader("🎤 Uszy Agenta")

    # Komponent nagrywający
    audio_input = mic_recorder(
        start_prompt="🔴 Nagraj",
        stop_prompt="⏹️ Stop",
        just_once=True,
        key='recorder'
    )

# === UI: GŁÓWNE OKNO CZATU ===
st.title("🤖 AI Super-Agent")
st.caption(f"Powered by {describe(st.session_state.provider)} & Python")

def _message_text(content):
    """Tekst z wiadomości: zwykły string albo lista części (tekst/obraz/audio)."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if p.get("type") == "text")


# Wyświetlanie historii czatu
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(_message_text(msg["content"]))
            # Obrazy i nagrania z poprzednich tur pomijamy dla czytelności.

    elif msg["role"] == "assistant":
        if msg.get("content"):
            with st.chat_message("assistant"):
                st.markdown(msg["content"])

    # === Wyświetlanie wykresów stworzonych przez Agenta ===
    elif msg["role"] == "tool":
        # Sprawdzamy, czy narzędzie zwróciło informację o stworzonym pliku graficznym
        resp = str(msg["content"])
        # Prosta heurystyka: jeśli odpowiedź zawiera ".png" lub ".jpg"
        if ".png" in resp or ".jpg" in resp:
            import glob
            # Szukamy najnowszego pliku w workspace
            files = glob.glob("agent_workspace/*.png") + glob.glob("agent_workspace/*.jpg")
            if files:
                latest_file = max(files, key=os.path.getmtime)
                with st.chat_message("assistant"):
                    st.image(latest_file, caption="Wygenerowany plik", width=400)

# === LOGIKA AGENTA ===

# 1. Pobieramy input tekstowy
prompt_text = st.chat_input("O co chcesz zapytać?")

# 2. Sprawdzamy, co zrobił użytkownik (Napisał czy Nagrał?)
user_action = None

if prompt_text:
    user_action = "text"
elif audio_input:
    user_action = "audio"

# Jeśli jest jakakolwiek akcja (Tekst lub Audio)
if user_action:
    user_parts = []  # części wiadomości w formacie OpenAI
    
    # --- SCENARIUSZ A: TEKST ---
    if user_action == "text":
        user_parts.append({"type": "text", "text": prompt_text})
        # Wyświetl w czacie
        with st.chat_message("user"):
            st.markdown(prompt_text)

    # --- SCENARIUSZ B: AUDIO (GŁOS) ---
    elif user_action == "audio":
        # Wyciągamy bajty z nagrania
        audio_bytes = audio_input['bytes']
        
        # Dodajemy plik audio dla modelu
        # (obsługują to np. Gemini i modele audio OpenAI; pozostali dostawcy zignorują nagranie)
        user_parts.append({"type": "input_audio", "input_audio": {"data": base64.b64encode(audio_bytes).decode(), "format": "wav"}})
        # Dodajemy instrukcję pomocniczą
        user_parts.append({"type": "text", "text": "Odsłuchaj to nagranie i wykonaj polecenie."})
        
        # Wyświetl odtwarzacz w czacie (żebyś widział, że wyszło)
        with st.chat_message("user"):
            st.audio(audio_bytes, format="audio/wav")
            st.caption("🎙️ Wiadomość głosowa")

    # --- WSPÓLNE: OBRAZ (Jeśli dodano w pasku bocznym) ---
    if image_input:
        img_byte_arr = io.BytesIO()
        image_input.save(img_byte_arr, format=image_input.format)
        img_bytes = img_byte_arr.getvalue()
        
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_input.format.lower()};base64,{base64.b64encode(img_bytes).decode()}"},
        })
        # Pokaż obrazek w czacie
        with st.chat_message("user"):
            st.image(image_input, width=200)

    # 3. Zapisz w historii
    st.session_state.messages.append({"role": "user", "content": user_parts})

    # 4. Uruchom Agenta
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        status_container = st.status("Thinking...", expanded=True)
        
        current_messages = st.session_state.messages.copy()
        MAX_ITERS = 20
        
        try:
            for i in range(MAX_ITERS):
                status_container.write(f"🔄 Iteracja {i+1}...")
                
                # Wywołanie API wybranego dostawcy
                response = complete(
                    current_messages,
                    system=system_prompt,
                    tools=get_tools(),
                    client=get_client(st.session_state.provider),
                    provider=st.session_state.provider,
                )

                # Dodajemy odpowiedź do historii (tymczasowej)
                assistant_message = message_to_dict(response.choices[0].message)
                current_messages.append(assistant_message)

                # Sprawdzamy czy agent chce zakończyć (brak wywołań funkcji)
                tool_calls = assistant_message.get("tool_calls")
                if not tool_calls:
                    status_container.update(label="Gotowe!", state="complete", expanded=False)
                    message_placeholder.markdown(assistant_message["content"] or "")

                    # Aktualizujemy główną pamięć sesji
                    st.session_state.messages = current_messages
                    save_memory(st.session_state.messages)
                    break

                # Jeśli są funkcje do wykonania:
                tool_messages = []

                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    try:
                        func_args = json.loads(tool_call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        func_args = {}

                    status_container.write(f"🛠️ Agent chce użyć: `{func_name}`")

                    # --- REVIEWER ---
                    if func_name == "write_file":
                        file_path = func_args.get("file_path", "")
                        if file_path.endswith(".py"):
                            status_container.info(f"🔍 Reviewer sprawdza kod: {file_path}")
                            content_to_review = func_args.get("content", "")
                            is_approved, feedback = review_code(content_to_review)

                            if not is_approved:
                                status_container.error(f"❌ Reviewer odrzucił kod: {feedback}")
                                tool_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call["id"],
                                    "content": json.dumps({"error": f"Security Review Failed: {feedback}"}, ensure_ascii=False),
                                })
                                continue
                            else:
                                status_container.success("✅ Reviewer zatwierdził kod.")

                    # --- HUMAN APPROVAL (Symulacja) ---
                    if func_name in SENSITIVE_FUNCTIONS:
                            status_container.warning(f"⚠️ Wykonuję wrażliwą akcję: {func_name}...")
                            time.sleep(1)

                    # --- WYKONANIE ---
                    result = call_function(tool_call, verbose=True)

                    # Wyświetl wynik w expanderze
                    status_container.code(f"Wynik: {result['content'][:200]}...")

                    tool_messages.append(result)

                # Dodajemy wyniki funkcji do historii
                current_messages.extend(tool_messages)

        except Exception as e:
            st.error(f"Błąd krytyczny: {e}")