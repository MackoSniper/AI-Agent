from llm_provider import complete
from prompts import reviewer_prompt


def review_code(code_content: str, client=None) -> tuple[bool, str]:
    """
    Wysyła kod do agenta-audytora.
    Zwraca: (czy_zatwierdzono, komentarz)
    """
    print("\n🔍 [REVIEWER] Analizuję kod...")

    try:
        response = complete(
            messages=[{"role": "user", "content": f"CODE TO REVIEW:\n```python\n{code_content}\n```"}],
            system=reviewer_prompt,
            temperature=0.0,
            client=client,
        )

        verdict = (response.choices[0].message.content or "").strip()

        # Przepuszczamy tylko dokładne "APPROVED".
        # Stare sprawdzenie `"APPROVED" in verdict` przepuszczało np. "REJECTED: this cannot be APPROVED".
        if verdict.strip('"').upper() == "APPROVED":
            print("✅ [REVIEWER] Kod zatwierdzony.")
            return True, "Code looks safe."

        print(f"❌ [REVIEWER] Odrzucono: {verdict}")
        return False, verdict or "Empty reviewer response."

    except Exception as e:
        print(f"⚠️ [REVIEWER] Błąd API: {e}")

        return False, f"Reviewer failed: {str(e)}"
