from llm_provider import complete
from prompts import reviewer_prompt


def review_code(code_content: str, client=None) -> tuple[bool, str]:
    """
    Sends the code to the auditor agent.
    Returns: (approved, comment)
    """
    print("\n🔍 [REVIEWER] Analyzing code...")

    try:
        response = complete(
            messages=[{"role": "user", "content": f"CODE TO REVIEW:\n```python\n{code_content}\n```"}],
            system=reviewer_prompt,
            temperature=0.0,
            client=client,
        )

        verdict = (response.choices[0].message.content or "").strip()

        # We only let through an exact "APPROVED".
        # The old check `"APPROVED" in verdict` let through e.g. "REJECTED: this cannot be APPROVED".
        if verdict.strip('"').upper() == "APPROVED":
            print("✅ [REVIEWER] Code approved.")
            return True, "Code looks safe."

        print(f"❌ [REVIEWER] Rejected: {verdict}")
        return False, verdict or "Empty reviewer response."

    except Exception as e:
        print(f"⚠️ [REVIEWER] API error: {e}")

        return False, f"Reviewer failed: {str(e)}"
