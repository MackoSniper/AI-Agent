from types import SimpleNamespace

import pytest

from reviewer import review_code


class FakeCompletions:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.text, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_client(text=None, error=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(text=text, error=error)))


@pytest.mark.parametrize("verdict", ["APPROVED", "  APPROVED\n", '"APPROVED"', "approved"])
def test_approved(verdict):
    ok, _ = review_code("print('hi')", client=fake_client(verdict))
    assert ok


@pytest.mark.parametrize(
    "verdict",
    [
        "REJECTED: infinite loop",
        "REJECTED: this cannot be APPROVED",  # stary kod przepuszczał to przez `in`
        "NOT APPROVED",
        "",
    ],
)
def test_rejected(verdict):
    ok, feedback = review_code("while True: pass", client=fake_client(verdict))
    assert not ok
    assert feedback


def test_api_error_rejects_code():
    ok, feedback = review_code("print(1)", client=fake_client(error=RuntimeError("quota")))
    assert not ok
    assert "quota" in feedback


def test_code_is_sent_to_model():
    client = fake_client("APPROVED")
    review_code("print('secret sauce')", client=client)
    sent = client.chat.completions.calls[0]["messages"][-1]["content"]
    assert "print('secret sauce')" in sent
