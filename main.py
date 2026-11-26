import argparse
import json
import sys

from call_function import call_function, get_tools
from config import MAX_ITERS
from llm_provider import complete, describe, get_client, message_to_dict
from prompts import system_prompt
from reviewer import review_code
from memory import load_memory, save_memory, clear_memory

SENSITIVE_FUNCTIONS = ["write_file", "run_python_file"]

def main():
    parser = argparse.ArgumentParser(description="AI Code Assistant")
    parser.add_argument("user_prompt", type=str, help="Prompt to send to the model")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    # === NOWOŚĆ: Flaga do czyszczenia pamięci ===
    parser.add_argument("--new", action="store_true", help="Start a fresh session (clear memory)")
    
    args = parser.parse_args()

    # Obsługa czyszczenia pamięci
    if args.new:
        clear_memory()

    # Dostawca wybierany zmienną LLM_PROVIDER w .env (patrz llm_provider.py)
    client = get_client()

    # === LOGIKA PAMIĘCI ===
    # 1. Wczytujemy starą historię
    messages = load_memory()

    # 2. Jeśli historia jest pusta, zaczynamy od zera. 
    #    Jeśli nie jest pusta, dopisujemy nową wiadomość użytkownika do istniejącej listy.
    messages.append({"role": "user", "content": args.user_prompt})
    
    if args.verbose:
        print(f"Provider: {describe()}")
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
    response = complete(messages, system=system_prompt, tools=get_tools(), client=client)

    if not response.choices:
        raise RuntimeError("LLM API response appears to be malformed")

    if verbose and getattr(response, "usage", None):
        print(f"[Tokens] Prompt: {response.usage.prompt_tokens} | Response: {response.usage.completion_tokens}")

    assistant_message = message_to_dict(response.choices[0].message)
    messages.append(assistant_message)

    tool_calls = assistant_message.get("tool_calls")
    if not tool_calls:
        return assistant_message["content"] or "(empty response)"

    tool_messages = []

    for tool_call in tool_calls:
        func_name = tool_call["function"]["name"]
        try:
            func_args = json.loads(tool_call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            func_args = {}

        def reject(reason):
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps({"error": reason}, ensure_ascii=False),
            })

        # === KROK 1: AUTOMATYCZNY AUDYT (REVIEWER) ===
        # Sprawdzamy kod tylko przy próbie zapisu pliku
        if func_name == "write_file":
            file_path = func_args.get("file_path", "")

            # Uruchamiamy Reviewera TYLKO dla plików .py
            # Pliki .txt, .json, .md są bezpieczne (chyba że to skrypt bash, ale skupiamy się na Pythonie)
            if file_path.endswith(".py"):
                is_approved, feedback = review_code(func_args.get("content", ""))

                if not is_approved:
                    reject(f"Security Review Failed: {feedback}. Please fix the code and try again.")
                    continue

        # === SECURITY CHECK (FAZA 1) ===
        if func_name in SENSITIVE_FUNCTIONS:
            print(f"\n⚠️  [SECURITY ALERT] Agent wants to execute: {func_name}")
            print(f"    Args: {func_args}")
            user_approval = input(">> Allow? (y/N): ").strip().lower()

            if user_approval != 'y':
                print("❌ Denied by user.")
                reject("User denied execution of this function.")
                continue

        result = call_function(tool_call, verbose)

        if verbose:
            print(f"-> Output: {result['content']}")

        tool_messages.append(result)

    messages.extend(tool_messages)

    save_memory(messages)

    return None

if __name__ == "__main__":
    main()
