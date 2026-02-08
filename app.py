import streamlit as st # type: ignore[import]
import os
import time
from dotenv import load_dotenv # type: ignore[import]
from google import genai
from google.genai import types # type: ignore[import]
from PIL import Image # type: ignore[import]
import io
import base64
from streamlit_mic_recorder import mic_recorder # type: ignore[import]


# Importujemy nasze moduły
from call_function import available_functions_tool, call_function
from prompts import system_prompt
from reviewer import review_code
from memory import load_memory, save_memory, clear_memory

# Konfiguracja strony
st.set_page_config(page_title="AI Agent Workspace", page_icon="🤖", layout="wide")

# Ładowanie zmiennych
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

# Funkcje wrażliwe wymagające zgody
SENSITIVE_FUNCTIONS = ["write_file", "run_python_file"]

# === INICJALIZACJA STANU (SESSION STATE) ===
if "messages" not in st.session_state:
    st.session_state.messages = load_memory()  # Ładujemy pamięć z pliku na start

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=api_key)

# === UI: PASEK BOCZNY ===
with st.sidebar:
    st.title("🔧 Panel Sterowania")
    if st.button("🧹 Wyczyść pamięć"):
        clear_memory()
        st.session_state.messages = []
        st.rerun()
    
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
st.caption("Powered by Gemini 2.5 Flash & Python")

# Wyświetlanie historii czatu
for msg in st.session_state.messages:
    if msg.role == "user":
        with st.chat_message("user"):
            st.markdown(msg.parts[0].text)
            # Jeśli użytkownik wysłał obrazek w poprzednich turach, tu byśmy musieli go odtworzyć,
            # ale w tej prostej wersji pomijamy wyświetlanie starych obrazków usera dla czytelności.
            
    elif msg.role == "model":
        text_content = ""
        for part in msg.parts:
            if part.text:
                text_content += part.text
        if text_content:
            with st.chat_message("assistant"):
                st.markdown(text_content)
    
    # === NOWOŚĆ: Wyświetlanie wykresów stworzonych przez Agenta ===
    elif msg.role == "tool":
        # Sprawdzamy, czy narzędzie zwróciło informację o stworzonym pliku graficznym
        for part in msg.parts:
            if part.function_response and part.function_response.response:
                resp = str(part.function_response.response)
                # Prosta heurystyka: jeśli odpowiedź zawiera ".png" lub ".jpg"
                if ".png" in resp or ".jpg" in resp:
                    import glob
                    # Szukamy najnowszego pliku w workspace
                    files = glob.glob("agent_workspace/*.png") + glob.glob("agent_workspace/*.jpg")
                    if files:
                        latest_file = max(files, key=os.path.getmtime)
                        # Jeśli plik jest świeży (z tej sesji)
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
    user_parts = []
    
    # --- SCENARIUSZ A: TEKST ---
    if user_action == "text":
        user_parts.append(types.Part(text=prompt_text))
        # Wyświetl w czacie
        with st.chat_message("user"):
            st.markdown(prompt_text)

    # --- SCENARIUSZ B: AUDIO (GŁOS) ---
    elif user_action == "audio":
        # Wyciągamy bajty z nagrania
        audio_bytes = audio_input['bytes']
        
        # Dodajemy plik audio dla modelu
        user_parts.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))
        # Dodajemy instrukcję pomocniczą
        user_parts.append(types.Part(text="Odsłuchaj to nagranie i wykonaj polecenie."))
        
        # Wyświetl odtwarzacz w czacie (żebyś widział, że wyszło)
        with st.chat_message("user"):
            st.audio(audio_bytes, format="audio/wav")
            st.caption("🎙️ Wiadomość głosowa")

    # --- WSPÓLNE: OBRAZ (Jeśli dodano w pasku bocznym) ---
    if image_input:
        img_byte_arr = io.BytesIO()
        image_input.save(img_byte_arr, format=image_input.format)
        img_bytes = img_byte_arr.getvalue()
        
        user_parts.append(
            types.Part.from_bytes(data=img_bytes, mime_type=f"image/{image_input.format.lower()}")
        )
        # Pokaż obrazek w czacie
        with st.chat_message("user"):
            st.image(image_input, width=200)

    # 3. Zapisz w historii
    st.session_state.messages.append(types.Content(role="user", parts=user_parts))

    # 4. Uruchom Agenta
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        status_container = st.status("Thinking...", expanded=True)
        
        current_messages = st.session_state.messages.copy()
        MAX_ITERS = 20
        
        try:
            for i in range(MAX_ITERS):
                status_container.write(f"🔄 Iteracja {i+1}...")
                
                # Wywołanie API Gemini
                response = st.session_state.client.models.generate_content(
                    model="gemini-2.5-flash", # Upewnij się, że masz tu dobry model (np. 2.0 Flash)
                    contents=current_messages,
                    config=types.GenerateContentConfig(
                        tools=[available_functions_tool],
                        system_instruction=system_prompt
                    ),
                )

                # Dodajemy odpowiedź kandydata do historii (tymczasowej)
                if response.candidates and response.candidates[0].content:
                    current_messages.append(response.candidates[0].content)

                # Sprawdzamy czy agent chce zakończyć (brak wywołań funkcji)
                if not response.function_calls:
                    status_container.update(label="Gotowe!", state="complete", expanded=False)
                    message_placeholder.markdown(response.text)
                    
                    # Aktualizujemy główną pamięć sesji
                    st.session_state.messages = current_messages
                    save_memory(st.session_state.messages)
                    break
                
                # Jeśli są funkcje do wykonania:
                function_responses = []
                
                for function_call in response.function_calls:
                    func_name = function_call.name
                    func_args = function_call.args
                    
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
                                rejection_part = types.Part.from_function_response(
                                    name=func_name,
                                    response={"error": f"Security Review Failed: {feedback}"}
                                )
                                function_responses.append(rejection_part)
                                continue 
                            else:
                                status_container.success("✅ Reviewer zatwierdził kod.")

                    # --- HUMAN APPROVAL (Symulacja) ---
                    if func_name in SENSITIVE_FUNCTIONS:
                            status_container.warning(f"⚠️ Wykonuję wrażliwą akcję: {func_name}...")
                            time.sleep(1)

                    # --- WYKONANIE ---
                    result = call_function(function_call, verbose=True)
                    
                    # Wyświetl wynik w expanderze
                    result_text = str(result.parts[0].function_response.response)[:200] + "..."
                    status_container.code(f"Wynik: {result_text}")
                    
                    function_responses.append(result.parts[0])

                # Dodajemy wyniki funkcji do historii
                current_messages.append(types.Content(role="tool", parts=function_responses))
                
        except Exception as e:
            st.error(f"Błąd krytyczny: {e}")