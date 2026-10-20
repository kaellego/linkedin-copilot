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

    def test_visible_review_button_overrides_stale_contact_title(self):
        signals = {
            "titulos": ["Informações de contato"],
            "botoes": ["Fechar", "Enviar candidatura"],
            "campos": [],
            "tem_cartao_curriculo": False,
            "tem_formulario": True,
            "quantidade_grupos_pergunta": 0,
        }
        self.assertEqual(self.detector._classify_screen("Informações de contato", signals), "review")

    def test_review_navigation_button_does_not_hide_unanswered_questions(self):
        signals = {
            "titulos": ["Perguntas adicionais"],
            "botoes": ["Fechar", "Revise sua candidatura Revisar"],
            "campos": [],
            "tem_cartao_curriculo": False,
            "tem_formulario": True,
            "quantidade_grupos_pergunta": 10,
        }
        self.assertEqual(self.detector._classify_screen("Perguntas adicionais", signals), "questions")

    def test_live_signals_ignore_hidden_modal_steps(self):
        class Element:
            def __init__(self, text="", visible=True, attrs=None):
                self.text = text
                self.visible = visible
                self.attrs = attrs or {}

            def is_displayed(self):
                return self.visible

            def get_attribute(self, name):
                return self.attrs.get(name)

            def find_elements(self, by, selector):
                return []

        contact_heading = Element("Informações de contato")
        hidden_review_heading = Element("Revise sua candidatura", visible=False)
        close = Element("Fechar", attrs={"aria-label": "Fechar"})
        hidden_submit = Element("Enviar candidatura", visible=False, attrs={"aria-label": "Enviar candidatura"})
        form = Element()
        modal = Element(attrs={"outerHTML": '<div role="dialog"><h3>Revise sua candidatura</h3><button>Enviar candidatura</button></div>'})
        modal.find_elements = lambda by, selector: {
            "h1, h2, h3, h4, [role='heading']": [contact_heading, hidden_review_heading],
            "button": [close, hidden_submit],
            "label[for]": [],
            "input:not([type='hidden']), textarea, select": [],
            ".fb-dash-form-element": [],
            ".jobs-document-upload-redesign-card__container": [],
            "form": [form],
        }.get(selector, [])
        self.detector.driver = Element()
        self.detector.driver.find_elements = lambda by, selector: [modal]

        signals = self.detector._collect_screen_signals()

        self.assertEqual(signals["titulos"], ["Informações de contato"])
        self.assertEqual(signals["botoes"], ["Fechar Fechar"])
        self.assertEqual(self.detector._classify_screen("Informações de contato", signals), "contact")

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
