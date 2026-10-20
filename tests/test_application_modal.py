import json
import unittest
from pathlib import Path

from pages.application_modal import ApplicationModal


FIXTURES = Path(__file__).parent / "fixtures"


class SavedHtmlScreenDetectionTests(unittest.TestCase):
    def setUp(self):
        self.detector = ApplicationModal.__new__(ApplicationModal)

    def classify(self, name):
        return self.detector._classify_saved_html(
            (FIXTURES / name).read_text(encoding="utf-8")
        )

    def test_detects_contact_screen(self):
        self.assertEqual(self.classify("contact.html"), "contact")

    def test_detects_resume_screen_from_card_signal(self):
        self.assertEqual(self.classify("resume.html"), "resume")

    def test_detects_additional_questions_screen(self):
        self.assertEqual(self.classify("additional_questions.html"), "questions")

    def test_detects_review_screen(self):
        self.assertEqual(self.classify("review.html"), "review")

    def test_keeps_unknown_screen_unknown(self):
        self.assertEqual(self.classify("unknown.html"), "unknown")

    def test_signals_include_required_fields_without_values(self):
        html = (FIXTURES / "contact.html").read_text(encoding="utf-8")
        signals = self.detector._signals_from_html(html)
        self.assertTrue(signals["campos"][0]["required"])
        self.assertNotIn("value", signals["campos"][0])
        self.assertEqual(signals["quantidade_grupos_pergunta"], 1)


if __name__ == "__main__":
    unittest.main()
