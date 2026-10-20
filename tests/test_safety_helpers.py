import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from selenium.common.exceptions import ElementClickInterceptedException

import config
from pages.application_modal import ApplicationModal
from utils.debug_artifacts import save_failure_context
from utils.privacy import sanitize_html, sanitize_text


class AnswerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.modal = ApplicationModal.__new__(ApplicationModal)

    def test_duplicate_question_labels_match_saved_answer(self):
        saved = "Voc\u00ea mora em Goi\u00e2nia/Aparecida de Goi\u00e2nia?\nVoc\u00ea mora em Goi\u00e2nia/Aparecida de Goi\u00e2nia?"
        current = "Mora em Goi\u00e2nia/Aparecida de Goi\u00e2nia?\nMora em Goi\u00e2nia/Aparecida de Goi\u00e2nia?"
        self.modal.answers = {saved: "Sim"}

        self.assertEqual(self.modal._clean_question_text(current), "Mora em Goi\u00e2nia/Aparecida de Goi\u00e2nia?")
        self.assertEqual(self.modal._cached_answer_for_question(current), "Sim")

    def test_ai_receives_local_verified_answer_context(self):
        self.modal.answers = {"Aceita trabalho presencial?": "Sim"}
        self.modal.ai_service = Mock()
        self.modal.ai_service.answer_question.return_value = "Sim"
        self.modal.status_queue = Mock()
        with (
            patch.object(config, "AI_ENABLED", True),
            patch.object(config, "AI_PROFILE_CONTEXT", ""),
            patch.object(config, "AI_BASE_URL", "http://127.0.0.1:8080/v1"),
        ):
            self.assertEqual(self.modal._ask_ai("Aceita presencial?", ["Sim", "N\u00e3o"]), "Sim")

        context = self.modal.ai_service.answer_question.call_args.kwargs["profile_context"]
        self.assertIn("Verified answer: Sim", context)

    def test_ai_review_pause_is_interruptible(self):
        self.modal.status_queue = Mock()
        self.modal.stop_event = Mock()
        self.modal.stop_event.is_set.return_value = False
        self.modal.stop_event.wait.return_value = False
        self.modal.pause_event = threading.Event()
        self.modal.pause_event.set()
        with patch.object(config, "AI_REVIEW_PAUSE_SECONDS", 2):
            self.modal._pause_after_ai_answer()
        self.modal.stop_event.wait.assert_called_once_with(timeout=2)

    def test_option_match_requires_full_option(self):
        self.assertEqual(self.modal._match_option("sim", ["Sim", "Não"]), "Sim")
        self.assertEqual(self.modal._match_option("sim, tenho experiência", ["Sim", "Não"]), "")

    def test_option_match_ignores_accents_and_case(self):
        self.assertEqual(self.modal._match_option("presencial", ["Presencial"]), "Presencial")
        self.assertEqual(self.modal._match_option("[Sim]", ["Sim", "Não"]), "Sim")

    def test_free_text_cache_is_never_automatic(self):
        self.assertFalse(self.modal._is_valid_cached_answer("Conte sua experiência", "Tenho experiência", []))

    def test_cached_option_must_still_be_available(self):
        self.assertTrue(self.modal._is_valid_cached_answer("Aceita presencial?", "Sim", ["Sim", "Não"]))
        self.assertFalse(self.modal._is_valid_cached_answer("Aceita presencial?", "Talvez", ["Sim", "Não"]))

    def test_required_field_blocks_progress_when_empty(self):
        class Field:
            tag_name = "input"

            def get_attribute(self, name):
                return {"type": "text", "name": "email", "value": "", "required": "true"}.get(name)

            def is_displayed(self):
                return True

            def is_selected(self):
                return False

        class Scope:
            def __init__(self, field):
                self.field = field

            def find_elements(self, by, selector):
                if selector == ".artdeco-inline-feedback--error":
                    return []
                if "required" in selector:
                    return [self.field]
                if selector in ("input", ":invalid"):
                    return [self.field] if selector == "input" else []
                return []

        class Driver:
            def __init__(self, scope):
                self.scope = scope

            def find_elements(self, by, selector):
                return [self.scope] if selector == "div[role='dialog'], .jobs-easy-apply-modal" else []

        field = Field()
        self.modal.driver = Driver(Scope(field))
        errors = self.modal._validate_current_form()
        self.assertTrue(any("Campo obrigatório" in error for error in errors))

    def test_required_field_passes_when_filled(self):
        class Field:
            tag_name = "input"

            def get_attribute(self, name):
                return {"type": "text", "name": "email", "value": "filled", "required": "true"}.get(name)

            def is_displayed(self):
                return True

            def is_selected(self):
                return False

        class Scope:
            def __init__(self, field):
                self.field = field

            def find_elements(self, by, selector):
                if selector == ".artdeco-inline-feedback--error":
                    return []
                if "required" in selector or selector == "input":
                    return [self.field]
                return []

        class Driver:
            def __init__(self, scope):
                self.scope = scope

            def find_elements(self, by, selector):
                return [self.scope] if selector == "div[role='dialog'], .jobs-easy-apply-modal" else []

        self.modal.driver = Driver(Scope(Field()))
        self.assertEqual(self.modal._validate_current_form(), [])

    def test_placeholder_select_is_not_a_valid_required_answer(self):
        self.assertTrue(self.modal._is_placeholder_option("Selecione uma opção"))
        self.assertTrue(self.modal._is_placeholder_option("Select an option"))
        self.assertFalse(self.modal._is_placeholder_option("Sim, tenho disponibilidade"))

    def test_intercepted_progress_click_falls_back_to_dom_click(self):
        element = Mock()
        element.click.side_effect = ElementClickInterceptedException("covered by select")
        self.modal.status_queue = Mock()
        self.modal.driver = Mock()

        self.modal._click_button(element)

        self.modal.driver.execute_script.assert_called_once()
        self.assertIs(self.modal.driver.execute_script.call_args.args[1], element)


class PrivacyTests(unittest.TestCase):
    def test_logs_redact_email_phone_and_url_query(self):
        value = sanitize_text("contato teste@example.com, telefone 62981847446 https://example.com/app?token=secret")
        self.assertNotIn("teste@example.com", value)
        self.assertNotIn("62981847446", value)
        self.assertNotIn("token=secret", value)

    def test_html_redacts_controls_and_query_values(self):
        html = sanitize_html('<input value="private"><textarea>private</textarea><a href="https://example.com/a?token=x">link</a>')
        self.assertNotIn('value="private"', html)
        self.assertNotIn("<textarea>private</textarea>", html)
        self.assertNotIn("?token=x", html)

    def test_failure_bundle_has_unique_sanitized_context(self):
        class FakeDriver:
            current_url = "https://www.linkedin.com/jobs/view/123?trackingId=private"

            def execute_script(self, script, selector):
                return '<div role="dialog"><input value="private"><h3>Currículo</h3></div>'

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(config, "DATA_DIR", root / "data"),
                patch.object(config, "DEBUG_DIR", root / "debug"),
                patch.object(config, "LOG_DIR", root / "logs"),
            ):
                first = Path(save_failure_context(FakeDriver(), "resume", "failed"))
                second = Path(save_failure_context(FakeDriver(), "resume", "failed"))
            self.assertNotEqual(first.name, second.name)
            metadata = json.loads((first / "resumo.json").read_text(encoding="utf-8"))
            snapshot = (first / "componente.html").read_text(encoding="utf-8")
            self.assertEqual(metadata["url"], "https://www.linkedin.com/jobs/view/123")
            self.assertNotIn('value="private"', snapshot)


if __name__ == "__main__":
    unittest.main()
