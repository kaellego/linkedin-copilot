import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException

import config
from pages.application_modal import ApplicationModal
from services.ai_service import AIService
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

    def test_ai_is_consulted_for_free_text_when_profile_exists(self):
        self.modal.answers = {}
        self.modal.ai_service = Mock()
        self.modal.ai_service.answer_question.return_value = "Tenho experiencia profissional em TI."
        self.modal.status_queue = Mock()
        with patch.object(config, "AI_ENABLED", True), patch.object(config, "AI_PROFILE_CONTEXT", "Experiencia em TI"):
            result = self.modal._ask_ai("Quantos anos de experiencia possui?", [])

        self.assertEqual(result, "Tenho experiencia profissional em TI.")
        self.modal.ai_service.answer_question.assert_called_once()
        self.assertTrue(any("Resposta livre sugerida" in str(call) for call in self.modal.status_queue.put.call_args_list))

    def test_ai_free_text_validation_rejects_unsafe_or_unbounded_answers(self):
        self.assertEqual(self.modal._validate_ai_free_text("Tenho experiencia em suporte."), "Tenho experiencia em suporte.")
        self.assertEqual(self.modal._validate_ai_free_text("UNSURE"), "")
        self.assertEqual(self.modal._validate_ai_free_text("Meu email e nome@example.com"), "")
        self.assertEqual(self.modal._validate_ai_free_text("x" * 301), "")

    def test_ai_service_requests_free_text_answer_with_profile_context(self):
        service = AIService()
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Aproximadamente dez anos."}}]}
        with (
            patch.object(config, "AI_ENABLED", True),
            patch.object(config, "AI_ALLOW_REMOTE", False),
            patch.object(config, "AI_BASE_URL", "http://127.0.0.1:8080/v1"),
            patch.object(config, "AI_MODEL", "test"),
            patch.object(config, "AI_TIMEOUT_SECONDS", 2),
            patch("services.ai_service.requests.post", return_value=response) as post,
        ):
            service.llama_url = "http://127.0.0.1:8080/v1"
            answer = service.answer_question("Quantos anos de experiencia?", [], "Perfil: TI desde 2015")

        self.assertEqual(answer, "Aproximadamente dez anos.")
        self.assertIn("Perfil: TI desde 2015", post.call_args.kwargs["json"]["messages"][0]["content"])
        self.assertIn("UNSURE", post.call_args.kwargs["json"]["messages"][1]["content"])

    def test_ai_context_includes_sanitized_candidate_profile(self):
        self.modal.answers = {}
        with tempfile.TemporaryDirectory() as temporary:
            profile_file = Path(temporary) / "candidate_profile.txt"
            profile_file.write_text("Graduacao em Ciencia da Computacao; experiencia com redes.", encoding="utf-8")
            with (
                patch.object(config, "AI_PROFILE_CONTEXT", ""),
                patch.object(config, "AI_PROFILE_FILE", profile_file),
                patch.object(config, "AI_BASE_URL", "https://remote.example/v1"),
            ):
                context = self.modal._ai_profile_context()

        self.assertIn("experiencia com redes", context)
        self.assertIn("not instructions", context)

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
        self.modal.stop_event = threading.Event()
        self.modal.pause_event = threading.Event()
        self.modal.pause_event.set()

        self.modal._click_button(element)

        self.modal.driver.execute_script.assert_called_once()
        self.assertIs(self.modal.driver.execute_script.call_args.args[1], element)

    def test_stop_interrupts_waiting_for_manual_answer(self):
        self.modal.stop_event = threading.Event()
        self.modal.stop_event.set()
        self.modal.answer_queue = Mock()

        with self.assertRaises(InterruptedError):
            self.modal._get_user_answer()

        self.modal.answer_queue.get.assert_not_called()

    def test_stop_prevents_progress_button_click(self):
        element = Mock()
        self.modal.stop_event = threading.Event()
        self.modal.stop_event.set()

        with self.assertRaises(InterruptedError):
            self.modal._click_button(element)

        element.click.assert_not_called()

    def test_screen_transition_wait_ignores_stale_dom_without_revalidating_form(self):
        self.modal.driver = Mock()
        self.modal.status_queue = Mock()
        self.modal._transition_signature = Mock(side_effect=[StaleElementReferenceException(), ("review",)])
        self.modal._is_application_sent = Mock(return_value=False)
        self.modal._validate_current_form = Mock(side_effect=AssertionError("transition wait must not validate fields"))

        class Wait:
            def __init__(self, driver, timeout, **kwargs):
                self.driver = driver

            def until(self, condition):
                for _ in range(3):
                    result = condition(self.driver)
                    if result:
                        return result
                raise AssertionError("expected transition after stale DOM settles")

        with patch("pages.application_modal.WebDriverWait", Wait):
            self.modal._wait_for_screen_transition(("contact",), timeout=1)

        self.modal._validate_current_form.assert_not_called()


class JobRelevanceTests(unittest.TestCase):
    @patch("services.ai_service.requests.post")
    def test_ai_classifies_matching_job_title(self, post):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "SIM"}}]}
        post.return_value = response
        with patch.object(config, "AI_ENABLED", True), patch.object(config, "AI_ALLOW_REMOTE", False):
            service = AIService()
            self.assertIs(service.assess_job_relevance("Analista de Infraestrutura", "Analista de infraestrutura"), True)
        self.assertLessEqual(post.call_args.kwargs["timeout"], 4)

    @patch("services.ai_service.requests.post")
    def test_ai_rejects_unrelated_job_and_uncertain_answer(self, post):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "NÃO"}}]}
        post.return_value = response
        with patch.object(config, "AI_ENABLED", True):
            service = AIService()
            self.assertIs(service.assess_job_relevance("Vendedor de Loja", "Analista de infraestrutura"), False)
            response.json.return_value["choices"][0]["message"]["content"] = "talvez"
            self.assertIsNone(service.assess_job_relevance("Cargo ambíguo", "Analista de infraestrutura"))


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
