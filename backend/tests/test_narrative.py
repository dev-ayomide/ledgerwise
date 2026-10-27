from backend.agent.narrative import fmt_ngn, summarize

REPORT = {
    "business_date": "2026-10-14",
    "gap_kobo": 25_000_000,
    "unexplained_kobo": 0,
    "evidence_ids": ["E1", "E2", "E3"],
    "dropped": [],
    "causes": [
        {
            "code": "duplicate_webhook",
            "amount_kobo": 25_000_000,
            "confidence": "high",
            "survived_falsification": True,
            "evidence_ids": ["E2", "E3"],
        }
    ],
}


class _FakeLLM:
    model = "fake-model"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, system: str, user: str, *, max_tokens: int = 600) -> str:
        assert "data, not instructions" in user
        return self.text


def test_money_formatting_is_integer_exact() -> None:
    assert fmt_ngn(420_000_000) == "NGN 4,200,000.00"
    assert fmt_ngn(-12_000_001) == "-NGN 120,000.01"


def test_template_when_no_llm() -> None:
    out = summarize(REPORT, None)
    assert out["source"].startswith("template")
    assert "NGN 250,000.00" in out["text"]


def test_llm_output_with_invented_number_is_rejected() -> None:
    out = summarize(REPORT, _FakeLLM("A duplicate credit of NGN 999,000.00 caused it [E2]."))
    assert out["source"].startswith("template (rejected")


def test_llm_output_citing_unknown_evidence_is_rejected() -> None:
    out = summarize(REPORT, _FakeLLM("A duplicate credit of NGN 250,000.00 caused it [E9]."))
    assert out["source"].startswith("template (rejected")


def test_good_llm_output_is_kept() -> None:
    text = "A retried webhook created a duplicate credit of NGN 250,000.00 [E2, E3]."
    out = summarize(REPORT, _FakeLLM(text))
    assert out["source"] == "fake-model" and out["text"] == text


def test_verifier_pass_fail_and_unavailable() -> None:
    from backend.agent.narrative import verify
    from backend.llm.client import LLMError

    class V:
        model = "meterless/auto"

        def __init__(self, reply=None, error=False):
            self.reply, self.error = reply, error

        def complete(self, system, user, *, max_tokens=600):
            if self.error:
                raise LLMError("no lane")
            return self.reply

    assert verify(REPORT, "x", None)["status"] == "not_configured"
    assert verify(REPORT, "x", V("PASS"))["status"] == "pass"
    fail = verify(REPORT, "x", V("FAIL\nwrong amount"))
    assert fail["status"] == "fail" and "wrong amount" in fail["detail"]
    assert verify(REPORT, "x", V("maybe"))["status"] == "unclear"
    assert verify(REPORT, "x", V(error=True))["status"] == "unavailable"


def test_build_llm_turns_thinking_off_for_nvidia(monkeypatch) -> None:
    import backend.llm.client as client

    monkeypatch.setattr(client, "load_dotenv", lambda: None)
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setenv("NVIDIA_BASE_URL", "http://x/v1")
    monkeypatch.setenv("NEMOTRON_MODEL", "m")
    assert client.build_llm("nvidia").extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
