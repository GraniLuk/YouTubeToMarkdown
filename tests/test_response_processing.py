"""
Tests for the response_processing utilities.
"""

import unittest

from yt2md.response_processing import process_model_response


class TestResponseProcessing(unittest.TestCase):
    def test_description_first_chunk(self):
        text = "DESCRIPTION: This is a test description\nSome content here\nMore content"
        processed_text, description = process_model_response(text, True)
        self.assertEqual(description, "This is a test description")
        self.assertEqual(processed_text, "Some content here\nMore content")

    def test_description_with_leading_whitespace(self):
        text = """DESCRIPTION:
                Kolacja ze śmiesznym zaskoczeniem: jak Cola Zero, choć zerowa kaloryczność, potrafi w pełni zburzyć Twój mikrobiom, podrażnić żołądek i podważyć odporność, a jej skuteczniejszym zamiennikiem okazała się bezpłatna woda.

                1. Wstęp
                Cola Zero jest często postrzegana jako bezpieczny przekąski – „zero kalorii, więc mogę pić bez końca”.
                To jedno z największych kłamstw dietetycznego świata: problem nie leży w kaloriach, lecz w tym, czego nie widzisz."""
        processed_text, description = process_model_response(text, True)
        self.assertEqual(description, "Kolacja ze śmiesznym zaskoczeniem: jak Cola Zero, choć zerowa kaloryczność, potrafi w pełni zburzyć Twój mikrobiom, podrażnić żołądek i podważyć odporność, a jej skuteczniejszym zamiennikiem okazała się bezpłatna woda.")
        self.assertEqual(processed_text, """
                1. Wstęp
                Cola Zero jest często postrzegana jako bezpieczny przekąski – „zero kalorii, więc mogę pić bez końca”.
                To jedno z największych kłamstw dietetycznego świata: problem nie leży w kaloriach, lecz w tym, czego nie widzisz.""")

    def test_no_description_first_chunk(self):
        text = "Some content here\nMore content"
        processed_text, description = process_model_response(text, True)
        self.assertEqual(description, "")
        self.assertEqual(processed_text, text)

    def test_opis_prefix(self):
        text = "OPIS: This is a test description in Polish\nSome content here\nMore content"
        processed_text, description = process_model_response(text, True)
        self.assertEqual(description, "This is a test description in Polish")
        self.assertEqual(processed_text, "Some content here\nMore content")

    def test_not_first_chunk(self):
        text = "DESCRIPTION: This should be ignored\nSome content here\nMore content"
        processed_text, description = process_model_response(text, False)
        self.assertEqual(description, "")
        self.assertEqual(processed_text, text)

    def test_empty_text(self):
        processed_text, description = process_model_response("", True)
        self.assertEqual(description, "")
        self.assertEqual(processed_text, "")

    def test_multiline_before_description(self):
        text = "Some header\nAnother line\nDESCRIPTION: This is a description\nActual content starts here"
        processed_text, description = process_model_response(text, True)
        self.assertEqual(description, "This is a description")
        self.assertEqual(processed_text, "Actual content starts here")

    def test_whitespace_and_case_tolerance(self):
        samples = [
            " description:  lower case\nContent",
            "  DESCRIPTION :  spaced colon\nContent",
            "\tOpis:  mixed case polish\nContent",
        ]
        expected_desc = [
            "lower case",
            "spaced colon",
            "mixed case polish",
        ]
        for s, d in zip(samples, expected_desc):
            processed_text, description = process_model_response(s, True)
            self.assertEqual(description, d)
            self.assertEqual(processed_text, "Content")


if __name__ == "__main__":
    unittest.main()
