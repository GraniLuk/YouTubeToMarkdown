"""Integration test for the Gemini generate_content flow."""

from unittest import mock

from google.genai import types

from yt2md.llm_strategies import GeminiStrategy


class DummyResponse:
    def __init__(self, text: str):
        self.text = text


def test_generate_content_api_integration():
    """Test that GeminiStrategy uses models.generate_content correctly."""
    strategy = GeminiStrategy()

    call_log = []

    class DummyClient:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                # Log the call parameters
                call_log.append(kwargs.copy())

                # Verify correct parameters are used
                assert "contents" in kwargs, "Should use 'contents' parameter"
                assert "config" in kwargs, "Should use 'config' parameter"
                assert kwargs["model"] == "test-model"

                chunk_num = len(call_log)
                if chunk_num > 1:
                    assert "continuation of the previous transcript chunk" in kwargs[
                        "contents"
                    ]

                # Return a response
                return DummyResponse(
                    text=f"DESCRIPTION: Test description\nChunk {chunk_num} response"
                )

    # Create a long transcript that will be chunked
    long_transcript = " ".join([f"word{i}" for i in range(6000)])

    with mock.patch("google.genai.Client", return_value=DummyClient()):
        result_text, description = strategy.analyze_transcript(
            transcript=long_transcript,
            api_key="test_key",
            model_name="test-model",
            output_language="English",
            category="IT",
            chunk_size=5000,
        )

        # Verify we made multiple calls
        assert len(call_log) > 1, f"Expected multiple chunks, got {len(call_log)}"

        assert "continuation of the previous transcript chunk" not in call_log[0][
            "contents"
        ]

        for call in call_log[1:]:
            assert "continuation of the previous transcript chunk" in call["contents"]

        # Verify all calls use correct parameters
        for call in call_log:
            assert "contents" in call
            assert "config" in call
            assert isinstance(call["config"], types.GenerateContentConfig)
            assert call["model"] == "test-model"

        # Verify description was extracted from first chunk
        assert description == "Test description"

        # Verify result contains all chunks
        assert "Chunk 1 response" in result_text
        assert "Chunk 2 response" in result_text

        print(f"✓ Test passed! Made {len(call_log)} API calls with correct parameters")
        print("✓ Verified continuation prompt chaining")
        print("✓ Verified correct parameter names (contents, config)")


if __name__ == "__main__":
    test_generate_content_api_integration()
    print("\n✅ All integration tests passed!")
