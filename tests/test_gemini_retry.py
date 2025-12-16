from unittest import mock

import pytest

from yt2md.llm_strategies import GeminiStrategy


class DummyOutput:
    def __init__(self, text: str):
        self.text = text


class DummyResp:
    def __init__(self, text: str, interaction_id: str = "test_id"):
        self.outputs = [DummyOutput(text)]
        self.id = interaction_id


def make_error(msg):
    return Exception(msg)


def test_gemini_retry_success_on_second_attempt(monkeypatch):
    strategy = GeminiStrategy()

    attempts = {"count": 0}

    class DummyClient:
        class interactions:  # type: ignore
            @staticmethod
            def create(**kwargs):  # noqa: D401
                attempts["count"] += 1
                if attempts["count"] < 2:
                    raise make_error("503 UNAVAILABLE The model is overloaded")
                return DummyResp("DESCRIPTION: Test desc\nFinal content")

    with mock.patch("google.genai.Client", return_value=DummyClient()):
        text, desc = strategy.analyze_transcript(
            "some transcript text", api_key="k", model_name="m"
        )
        assert attempts["count"] == 2
        assert "Final content" in text
        assert desc == "Test desc"


def test_gemini_retry_exhaust(monkeypatch):
    strategy = GeminiStrategy()

    class DummyClientFail:
        class interactions:  # type: ignore
            @staticmethod
            def create(**kwargs):  # noqa: D401
                raise make_error("503 service unavailable again")

    with mock.patch("google.genai.Client", return_value=DummyClientFail()):
        with pytest.raises(Exception) as exc:
            strategy.analyze_transcript("short text", api_key="k", model_name="m")
        # Ensure our overload message present
        assert "503" in str(exc.value).lower()
