from unittest import mock

from yt2md.llm_strategies import GeminiStrategy


class DummyResp:
    def __init__(self, text: str):
        self.text = text


def test_gemini_defaults_when_no_retry_kwargs(monkeypatch):
    # Simulate successful first call; ensure no TypeError from None parsing
    class DummyClient:
        class models:  # type: ignore
            @staticmethod
            def generate_content(**kwargs):  # noqa: D401
                return DummyResp("DESCRIPTION: D\nBody")

    strategy = GeminiStrategy()
    with mock.patch("google.genai.Client", return_value=DummyClient()):
        text, desc = strategy.analyze_transcript(
            "abc", api_key="k", model_name="m"
        )  # Uses fixed internal defaults
        assert desc == "D"
        assert "Body" in text
