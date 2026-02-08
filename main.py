import argparse
import os
import sys

from dotenv import load_dotenv # type: ignore[import]
from google import genai
from google.genai import types # type: ignore[import]

from call_function import available_functions_tool, call_function
from config import MAX_ITERS
from prompts import system_prompt
from reviewer import review_code
from memory import load_memory, save_memory, clear_memory

SENSITIVE_FUNCTIONS = ["write_file", "run_python_file"]

def main():
    parser = argparse.ArgumentParser(description="AI Code Assistant")
    parser.add_argument("user_prompt", type=str, help="Prompt to send to Gemini")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    # === NOWOŚĆ: Flaga do czyszczenia pamięci ===
    parser.add_argument("--new", action="store_true", help="Start a fresh session (clear memory)")
    
    args = parser.parse_args()

    # Obsługa czyszczenia pamięci
    if args.new:
        clear_memory()

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")

    client = genai.Client(api_key=api_key)

    # === LOGIKA PAMIĘCI ===
    # 1. Wczytujemy starą historię
    messages = load_memory()

    # 2. Jeśli historia jest pusta, zaczynamy od zera. 
    #    Jeśli nie jest pusta, dopisujemy nową wiadomość użytkownika do istniejącej listy.
    messages.append(types.Content(role="user", parts=[types.Part(text=args.user_prompt)]))
    
    if args.verbose:
        print(f"User prompt: {args.user_prompt}\n")
        print(f"[MEMORY] Loaded {len(messages)-1} previous messages from context.")

    # Główna pętla myślenia
    for i in range(MAX_ITERS):
        try:
            final_response = generate_content(client, messages, args.verbose)
            
            # Po każdej udanej turze ZAPISUJEMY stan pamięci
            save_memory(messages)

            if final_response:
                print(final_response)
                return
                
        except Exception as e:
            print(f"Error in iteration {i}: {e}")
            break

    print(f"Maximum iterations ({MAX_ITERS}) reached")
    sys.exit(1)


def generate_content(client, messages, verbose):
    response = client.models.generate_content(
        model="gemini-2.5-flash", 
        contents=messages,
        config=types.GenerateContentConfig(
            tools=[available_functions_tool], 
            system_instruction=system_prompt
        ),
    )
    
    if not response.usage_metadata:
        raise RuntimeError("Gemini API response appears to be malformed")

    if verbose:
        print(f"[Tokens] Prompt: {response.usage_metadata.prompt_token_count} | Response: {response.usage_metadata.candidates_token_count}")

    if response.candidates:
        for candidate in response.candidates:
            if candidate.content:
                messages.append(candidate.content)

    if not response.function_calls:
        return response.text

    function_responses = []
    
    for function_call in response.function_calls:
        func_name = function_call.name
        func_args = function_call.args
        
        # === REVIEWER (FAZA 3) ===
        # === KROK 1: AUTOMATYCZNY AUDYT (REVIEWER) ===
        # Sprawdzamy kod tylko przy próbie zapisu pliku
        if func_name == "write_file":
            # Pobieramy nazwę pliku, żeby sprawdzić rozszerzenie
            file_path = func_args.get("file_path", "")
            
            # Uruchamiamy Reviewera TYLKO dla plików .py
            # Pliki .txt, .json, .md są bezpieczne (chyba że to skrypt bash, ale skupiamy się na Pythonie)
            if file_path.endswith(".py"):
                content_to_review = func_args.get("content", "")
                
                is_approved, feedback = review_code(content_to_review)
                
                if not is_approved:
                    rejection_part = types.Part.from_function_response(
                        name=func_name,
                        response={"error": f"Security Review Failed: {feedback}. Please fix the code and try again."}
                    )
                    function_responses.append(rejection_part)
                    continue 
        # =============================================

        # === SECURITY CHECK (FAZA 1) ===
        if func_name in SENSITIVE_FUNCTIONS:
            print(f"\n⚠️  [SECURITY ALERT] Agent wants to execute: {func_name}")
            print(f"    Args: {func_args}")
            user_approval = input(">> Allow? (y/N): ").strip().lower()
            
            if user_approval != 'y':
                print("❌ Denied by user.")
                rejection_part = types.Part.from_function_response(
                    name=func_name,
                    response={"error": "User denied execution of this function."}
                )
                function_responses.append(rejection_part)
                continue 

        result = call_function(function_call, verbose)
        
        if (
            not result.parts
            or not result.parts[0].function_response
            or not result.parts[0].function_response.response
        ):
            raise RuntimeError(f"Empty function response for {func_name}")
            
        if verbose:
            print(f"-> Output: {result.parts[0].function_response.response}")
            
        function_responses.append(result.parts[0])

    messages.append(types.Content(role="tool", parts=function_responses))
    
    save_memory(messages)
    
    return None

if __name__ == "__main__":
    main()