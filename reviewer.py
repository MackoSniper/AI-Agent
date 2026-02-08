import os
from google import genai
from google.genai import types # type: ignore[import]
from dotenv import load_dotenv # type: ignore[import]
from prompts import reviewer_prompt


load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in reviewer.py")

client = genai.Client(api_key=api_key)

def review_code(code_content: str) -> tuple[bool, str]:
    """
    Wysyła kod do agenta-audytora.
    Zwraca: (czy_zatwierdzono, komentarz)
    """
    print("\n🔍 [REVIEWER] Analizuję kod...")
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=[
                types.Content(role="user", parts=[types.Part(text=f"CODE TO REVIEW:\n```python\n{code_content}\n```")]),
            ],
            config=types.GenerateContentConfig(
                system_instruction=reviewer_prompt,
                temperature=0.0, 
            ),
        )
        
        verdict = response.text.strip()
        
        if "APPROVED" in verdict:
            print("✅ [REVIEWER] Kod zatwierdzony.")
            return True, "Code looks safe."
        else:
            print(f"❌ [REVIEWER] Odrzucono: {verdict}")
            return False, verdict

    except Exception as e:
        print(f"⚠️ [REVIEWER] Błąd API: {e}")
        
        return False, f"Reviewer failed: {str(e)}"