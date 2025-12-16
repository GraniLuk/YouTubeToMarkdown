"""
Integration test to verify the Interactions API implementation.
This test mocks the API calls to verify the correct flow without hitting rate limits.
"""

from unittest import mock

from google.genai import types

from yt2md.llm_strategies import GeminiStrategy


class DummyOutput:
    def __init__(self, text: str):
        self.text = text


class DummyInteractionResponse:
    def __init__(self, text: str, interaction_id: str):
        self.outputs = [DummyOutput(text)]
        self.id = interaction_id


def test_interactions_api_integration():
    """Test that the GeminiStrategy correctly uses the Interactions API."""
    strategy = GeminiStrategy()

    call_log = []

    class DummyClient:
        class interactions:
            @staticmethod
            def create(**kwargs):
                # Log the call parameters
                call_log.append(kwargs.copy())

                # Verify correct parameters are used
                assert "input" in kwargs, "Should use 'input' parameter"
                assert "generation_config" in kwargs, (
                    "Should use 'generation_config' parameter"
                )
                assert kwargs["model"] == "test-model"

                # Check if previous_interaction_id is correctly passed
                chunk_num = len(call_log)
                if chunk_num > 1:
                    assert "previous_interaction_id" in kwargs
                    assert kwargs["previous_interaction_id"] == f"id_{chunk_num - 1}"

                # Return a response
                return DummyInteractionResponse(
                    text=f"DESCRIPTION: Test description\nChunk {chunk_num} response",
                    interaction_id=f"id_{chunk_num}",
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

        # Verify first call doesn't have previous_interaction_id
        assert "previous_interaction_id" not in call_log[0]

        # Verify subsequent calls have previous_interaction_id
        for i, call in enumerate(call_log[1:], start=1):
            assert "previous_interaction_id" in call
            assert call["previous_interaction_id"] == f"id_{i}"

        # Verify all calls use correct parameters
        for call in call_log:
            assert "input" in call
            assert "generation_config" in call
            assert isinstance(call["generation_config"], types.GenerateContentConfig)
            assert call["model"] == "test-model"

        # Verify description was extracted from first chunk
        assert description == "Test description"

        # Verify result contains all chunks
        assert "Chunk 1 response" in result_text
        assert "Chunk 2 response" in result_text

        print(f"✓ Test passed! Made {len(call_log)} API calls with correct parameters")
        print("✓ Verified previous_interaction_id chaining")
        print("✓ Verified correct parameter names (input, generation_config)")


if __name__ == "__main__":
    test_interactions_api_integration()
    print("\n✅ All integration tests passed!")
