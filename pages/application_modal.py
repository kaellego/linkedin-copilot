# pages/application_modal.py
import time
import threading
import json
import os
import unicodedata
from html.parser import HTMLParser
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from pages.base_page import BasePage
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from services.ai_service import AIService
import config
from utils.debug_artifacts import save_failure_context
from utils.privacy import sanitize_text


class _ModalSignalsParser(HTMLParser):
    """Extrai somente rótulos e estrutura, nunca valores dos campos, de um HTML salvo."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings = []
        self.buttons = []
        self.fields = []
        self.question_groups = 0
        self.questions = []
        self.has_form = False
        self.has_resume_card = False
        self._captures = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
        if tag not in void_tags:
            for capture in self._captures:
                capture["depth"] += 1
        if tag in {"h1", "h2", "h3", "h4"} or attrs.get("role") == "heading":
            self._captures.append({"kind": "heading", "depth": 1, "text": []})
        elif tag == "button":
            self._captures.append({"kind": "button", "depth": 1, "text": [], "label": attrs.get("aria-label", "")})
        if "fb-dash-form-element" in classes:
            self._captures.append({"kind": "question", "depth": 1, "text": []})
        if tag == "form":
            self.has_form = True
        if "fb-dash-form-element" in classes:
            self.question_groups += 1
        if "jobs-document-upload-redesign-card__container" in classes:
            self.has_resume_card = True
        if tag in {"input", "textarea", "select"}:
            self.fields.append({
                "type": attrs.get("type") or tag,
                "name": attrs.get("name", ""),
                "id": attrs.get("id", ""),
                "label": attrs.get("aria-label") or attrs.get("placeholder", ""),
                "required": "required" in attrs or attrs.get("aria-required") == "true",
            })

    def handle_data(self, data):
        for capture in self._captures:
            capture["text"].append(data)

    def handle_endtag(self, tag):
        completed = []
        for capture in self._captures:
            capture["depth"] -= 1
            if capture["depth"] <= 0:
                completed.append(capture)
        self._captures = [capture for capture in self._captures if capture["depth"] > 0]
        for capture in completed:
            text = " ".join(" ".join(capture["text"]).split())
            if capture["kind"] == "heading" and text:
                self.headings.append(text)
            elif capture["kind"] == "button":
                label = text or capture.get("label", "")
                if label:
                    self.buttons.append(label)
            elif capture["kind"] == "question" and text:
                self.questions.append(text)

class ApplicationModal(BasePage):
    """
    Versão definitiva do modal, com a máquina de estados precisa para seguir
    o fluxo de 4 etapas: Contato -> Currículo -> Perguntas -> Revisão -> Envio.
    """
    
    # --- Locators ---
    MODAL_HEADER_TITLE = (By.CSS_SELECTOR, "div[data-test-modal][role='dialog'] .ph5 h3")
    MODAL_FALLBACK_TITLE = (By.CSS_SELECTOR, "div[data-test-modal][role='dialog'] .ph5 h4")
    WORK_EXPERIENCE_TITLE = (By.CSS_SELECTOR, "div[data-test-modal][role='dialog'] h3.t-16")
    MODAL_FORM_TITLE = (By.CSS_SELECTOR, "div.jobs-easy-apply-modal h3.t-16")
    FORM_GROUPS = (By.CSS_SELECTOR, ".fb-dash-form-element")
    TEXT_INPUTS = (By.CSS_SELECTOR, "input:not([type='radio']):not([type='checkbox']):not([type='file']):not([type='hidden']), textarea")
    
    # Botões de progresso específicos para cada etapa
    NEXT_BUTTON = (By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
    NEXT_BUTTON_FALLBACK = (By.CSS_SELECTOR, "button[aria-label='Avançar para próxima etapa']")
    OPTIONAL_NEXT_BUTTON = (By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
    BUTTON_BY_NEXT_TEXT = (By.XPATH, "//div[contains(@class, 'jobs-easy-apply-modal')]//button[normalize-space()='Avançar']")
    REVIEW_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Revise sua candidatura']")
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Enviar candidatura']")
    
    DONE_BUTTON = (By.XPATH, "//button[contains(., 'Concluído')]")
    APPLICATION_SENT_MODAL = (By.CSS_SELECTOR, "div[data-test-modal][role='dialog'] h2#post-apply-modal")
    SELECTED_RESUME_CARD = (By.CSS_SELECTOR, ".jobs-document-upload-redesign-card__container--selected")
    ANY_RESUME_CARD = (By.CSS_SELECTOR, ".jobs-document-upload-redesign-card__container")
    RESUME_CARD_LABEL = (By.TAG_NAME, "label")
    VALIDATION_ERROR = (By.CSS_SELECTOR, ".artdeco-inline-feedback--error")
    UPLOAD_INPUT = (By.CSS_SELECTOR, 'input[type="file"]')

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event, answers_dict: dict):
        super().__init__(driver)
        self.status_queue = status_queue
        self.answer_queue = answer_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.answers = self._load_answers()
        self.ai_service = AIService()

    def _load_answers(self) -> dict:
        """Carrega o arquivo de respostas conhecidas."""
        if os.path.exists(config.ANSWERS_FILE):
            try:
                with open(config.ANSWERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError): return {}
        return {}

    def _save_answers(self):
        """Salva o dicionário de respostas no arquivo JSON."""
        try:
            config.ensure_runtime_dirs()
            with open(config.ANSWERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.answers, f, indent=4, ensure_ascii=False)
            if os.name != "nt":
                os.chmod(config.ANSWERS_FILE, 0o600)
        except IOError as e:
            self.status_queue.put(f"ERRO: Não foi possível salvar o arquivo de respostas: {sanitize_text(e)}")

    def _normalize_question(self, text: str) -> str:
        """Canonicalize repeated labels and an optional leading "voce"."""
        normalized_lines = []
        for line in (text or "").replace("*", "").splitlines():
            line = " ".join(self._screen_key(line).split())
            if line.startswith("voce "):
                line = line[5:]
            if line and line not in normalized_lines:
                normalized_lines.append(line)
        return " ".join(normalized_lines)

    def _clean_question_text(self, text: str) -> str:
        """Remove duplicate lines generated by nested labels in the form."""
        lines = []
        seen = set()
        for line in (text or "").splitlines():
            line = " ".join(line.split())
            key = self._normalize_question(line)
            if line and key not in seen:
                lines.append(line)
                seen.add(key)
        return "\n".join(lines)

    def _cached_answer_for_question(self, question: str) -> str:
        normalized = self._normalize_question(question)
        matches = [
            str(answer).strip()
            for saved_question, answer in self.answers.items()
            if self._normalize_question(saved_question) == normalized and str(answer).strip()
        ]
        if not matches or len({self._screen_key(answer) for answer in matches}) > 1:
            return ""
        return matches[0]

    def _ai_profile_context(self) -> str:
        """Use saved answers as context only when the endpoint is local."""
        from urllib.parse import urlsplit

        context_parts = [config.AI_PROFILE_CONTEXT] if config.AI_PROFILE_CONTEXT else []
        try:
            host = urlsplit(config.AI_BASE_URL).hostname
        except ValueError:
            host = None
        if host in {"localhost", "127.0.0.1", "::1"}:
            history = [
                f"Verified question: {question}\nVerified answer: {answer}"
                for question, answer in self.answers.items()
                if str(question).strip() and str(answer).strip()
            ]
            if history:
                context_parts.append("Previously verified answers:\n" + "\n\n".join(history[-40:]))
        return "\n\n".join(context_parts)

    def _get_available_options(self, group) -> list:
        options = []
        try:
            select_element = group.find_element(By.TAG_NAME, "select")
            options.extend(
                option.text.strip()
                for option in Select(select_element).options
                if option.text.strip()
            )
        except NoSuchElementException:
            pass

        try:
            if group.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"):
                options.extend(
                    label.text.strip()
                    for label in group.find_elements(By.TAG_NAME, "label")
                    if label.text.strip()
                )
        except NoSuchElementException:
            pass

        return list(dict.fromkeys(options))

    def _ask_ai(self, question: str, options: list) -> str:
        if not config.AI_ENABLED:
            self.status_queue.put("IA nao consultada: AI_ENABLED esta desligada na configuracao.")
            return ""
        if not options:
            self.status_queue.put("IA nao consultada: pergunta sem opcoes; requer intervencao manual.")
            return ""
        profile_context = self._ai_profile_context()
        if not profile_context:
            self.status_queue.put("IA nao consultada: falta contexto de perfil ou respostas confirmadas.")
            return ""
        try:
            answer = str(self.ai_service.answer_question(
                question, options, profile_context=profile_context
            ) or "").strip()
            if answer and answer.upper() != "UNSURE":
                self.status_queue.put("Resposta sugerida pela IA; validando opcao disponivel.")
            elif answer.upper() == "UNSURE":
                self.status_queue.put("IA consultada, mas nao encontrou resposta segura no contexto.")
            else:
                self.status_queue.put("AVISO: IA indisponivel ou resposta vazia.")
            return answer
        except Exception:
            self.status_queue.put("AVISO: IA indisponivel; sera necessaria resposta manual.")
            return ""

    def _match_option(self, answer: str, options: list) -> str:
        normalized_answer = self._screen_key(answer.strip()).strip(" \t\r\n[](){}\"'`.,:;")
        for option in options:
            if self._screen_key(option.strip()) == normalized_answer:
                return option
        return ""

    def _is_valid_cached_answer(self, question: str, answer: str, options: list) -> bool:
        normalized_question = self._normalize_question(question)
        normalized_answer = answer.strip().lower()
        if not normalized_answer or normalized_answer == normalized_question:
            return False
        if options:
            return bool(self._match_option(answer, options))
        # Respostas livres dependem do contexto e nunca são reaproveitadas automaticamente.
        return False

    def _check_control_signals(self):
        """Verifica os eventos de pausa e parada, com lógica de keep-alive."""
        if self.stop_event.is_set():
            raise InterruptedError("Sinal de parada recebido.")
        if not self.pause_event.is_set():
            self.status_queue.put("Status: Pausado...")
            while not self.pause_event.is_set():
                resumed = self.pause_event.wait(timeout=15)
                if resumed: break
                try:
                    _ = self.driver.title
                    self.status_queue.put("(Mantendo a sessão ativa...)")
                except Exception as e:
                    self.status_queue.put(f"Erro no keep-alive: {sanitize_text(e)}.")
                if self.stop_event.is_set():
                    raise InterruptedError("Sinal de parada recebido durante a pausa.")
            self.status_queue.put("Status: Retomando...")

    def _pause_after_ai_answer(self):
        seconds = config.AI_REVIEW_PAUSE_SECONDS
        if seconds <= 0:
            return
        self.status_queue.put(f"Pausa para revisar a resposta da IA ({seconds:g}s)...")
        if self.stop_event.wait(timeout=seconds):
            raise InterruptedError("Processo interrompido durante a revisao da resposta da IA.")
        self._check_control_signals()

    def _click_optional_next(self):
        """Clica rapidamente no avanço da etapa opcional, sem esperar 25 segundos."""
        locators = (
            self.OPTIONAL_NEXT_BUTTON,
            self.NEXT_BUTTON,
            self.BUTTON_BY_NEXT_TEXT,
            self.REVIEW_BUTTON,
        )
        last_error = None
        for locator in locators:
            try:
                previous = self._transition_signature()
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable(locator)
                )
                self._click_button(element)
                self._wait_for_screen_transition(previous)
                return
            except (TimeoutException, StaleElementReferenceException) as error:
                last_error = error
        raise TimeoutException(f"Botão de avanço da etapa opcional não encontrado: {last_error}")

    def _click_next_button(self):
        """Avança uma etapa usando o atributo atual ou o aria-label legado."""
        last_error = None
        for locator in (self.NEXT_BUTTON, self.NEXT_BUTTON_FALLBACK):
            try:
                previous = self._transition_signature()
                element = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable(locator)
                )
                self._click_button(element)
                self._wait_for_screen_transition(previous)
                return
            except (TimeoutException, StaleElementReferenceException) as error:
                last_error = error
        raise TimeoutException(f"Botão 'Avançar' não encontrado: {last_error}")

    def _click_modal_button(self, locator, timeout: int = 4):
        previous = self._transition_signature()
        element = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable(locator))
        self._click_button(element)
        self._wait_for_screen_transition(previous)

    def _click_button(self, element):
        """Tenta o clique normal; se outro controle cobrir o ponto, aciona o botão no DOM."""
        try:
            element.click()
        except ElementClickInterceptedException:
            self.status_queue.put("Clique do botão interceptado por outro campo; tentando pelo controle da tela.")
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'}); arguments[0].click();",
                element,
            )

    def _transition_signature(self):
        try:
            signals = self._collect_screen_signals()
            return (
                tuple(signals["titulos"]),
                tuple(signals["botoes"]),
                tuple(signals["perguntas"]),
                signals["quantidade_grupos_pergunta"],
                signals["tem_cartao_curriculo"],
            )
        except Exception:
            return self._screen_key(self._get_current_screen_title())

    def _wait_for_screen_transition(self, previous, timeout: float = None):
        timeout = timeout or config.TRANSITION_WAIT_SECONDS
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=0.2).until(
                lambda _: self._transition_signature() != previous
                or self._is_application_sent()
                or bool(self._validate_current_form())
            )
        except TimeoutException:
            self.status_queue.put("Aguardando transição concluída; a tela ainda não confirmou mudança.")

    def _get_current_screen_title(self) -> str:
        """
        Identifica a tela atual do modal de forma robusta, testando múltiplos 
        seletores em ordem de prioridade.
        """
        # Lista de seletores para testar em ordem de importância
        title_locators = [
            self.MODAL_HEADER_TITLE,       # Seletor antigo principal (.ph5 h3)
            self.MODAL_FALLBACK_TITLE,     # Seletor antigo de fallback (.ph5 h4)
            self.WORK_EXPERIENCE_TITLE,    # Novo seletor para "Work Experience" (h3.t-16)
            self.MODAL_FORM_TITLE,         # Título do formulário do Easy Apply atual
        ]

        for locator in title_locators:
            try:
                # Tenta encontrar o elemento sem esperar muito, para ser rápido
                title_element = self.driver.find_element(*locator)
                title_text = title_element.text.strip().lower()
                
                # Se encontrou o elemento E ele tem texto, achamos o título
                if title_text:
                    return title_text
            except NoSuchElementException:
                # Se não encontrou, simplesmente continua para o próximo seletor da lista
                continue

        # O LinkedIn troca classes e estrutura do cabeçalho com frequência.
        # Procure títulos sem depender dessas classes, sempre dentro do modal.
        for locator in (
            (By.CSS_SELECTOR, "div[role='dialog'] h1, div[role='dialog'] h2, div[role='dialog'] h3, div[role='dialog'] h4"),
            (By.CSS_SELECTOR, ".jobs-easy-apply-modal h1, .jobs-easy-apply-modal h2, .jobs-easy-apply-modal h3, .jobs-easy-apply-modal h4"),
            (By.CSS_SELECTOR, "div[role='dialog'] [role='heading']"),
        ):
            for title_element in self.driver.find_elements(*locator):
                title_text = title_element.text.strip().lower()
                if title_text and title_element.get_attribute("id") != "jobs-apply-header" and len(title_text) < 120:
                    return title_text

        # O título da empresa fica no h2#jobs-apply-header e não identifica a etapa.
        # O HTML atual mantém o formulário e o botão Avançar mesmo quando o h3
        # ainda não foi renderizado pelo navegador.
        try:
            self.driver.find_element(By.CSS_SELECTOR, "div.jobs-easy-apply-modal form")
            self.driver.find_element(*self.NEXT_BUTTON)
            return "informações de contato"
        except NoSuchElementException:
            pass
        
        # Se o loop terminar e nenhum título for encontrado
        self.status_queue.put("ERRO: Nenhum seletor de título conhecido foi encontrado no modal.")
        return "unknown"

    def _collect_screen_signals(self) -> dict:
        """Coleta evidências visíveis do modal para classificar etapas sem título."""
        for selector in ("div[role='dialog']", ".jobs-easy-apply-modal"):
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                return self._signals_from_html(elements[0].get_attribute("outerHTML") or "")
        return self._signals_from_html("")

    @staticmethod
    def _signals_from_html(html: str) -> dict:
        parser = _ModalSignalsParser()
        parser.feed(html or "")
        return {
            "titulos": parser.headings[:20],
            "botoes": parser.buttons[:30],
            "perguntas": parser.questions[:30],
            "campos": parser.fields[:50],
            "quantidade_grupos_pergunta": parser.question_groups,
            "tem_formulario": parser.has_form,
            "tem_cartao_curriculo": parser.has_resume_card,
        }

    def _classify_saved_html(self, html: str) -> str:
        """Classifica um snapshot salvo offline, também usado pelos testes."""
        signals = self._signals_from_html(html)
        title = signals["titulos"][0] if signals["titulos"] else "unknown"
        return self._classify_screen(title, signals)

    def _classify_screen(self, title: str, signals: dict) -> str:
        """Retorna o estado canônico da tela usando título e controles presentes."""
        key = self._screen_key(title)
        if "revise sua candidatura" in key or "review your application" in key:
            return "review"
        if "informacoes de contato" in key or "contact information" in key or "contact info" in key:
            return "contact"
        if "curriculo" in key or "resume" in key:
            return "resume"
        if "work experience" in key:
            return "work_experience"
        if "marque esta vaga como preferencial" in key or "top choice" in key:
            return "optional"
        if any(term in key for term in ("perguntas adicionais", "additional questions", "autorizacao de trabalho", "work authorization", "home address")):
            return "questions"

        button_text = self._screen_key(" ".join(signals["botoes"]))
        heading_text = self._screen_key(" ".join(signals["titulos"]))
        field_text = self._screen_key(" ".join(
            f"{field['name']} {field['id']} {field['label']}" for field in signals["campos"]
        ))
        # Os botões de envio e revisão são sinais mais fortes que campos genéricos.
        if "enviar candidatura" in button_text or "submit application" in button_text:
            return "review"
        if signals["tem_cartao_curriculo"]:
            return "resume"
        if "work experience" in heading_text:
            return "work_experience"
        if "informacoes de contato" in heading_text or "contact information" in heading_text:
            return "contact"
        if signals["quantidade_grupos_pergunta"] and signals["tem_formulario"]:
            return "questions"
        # Contato só é inferido por campos identificáveis, sem usar formulário genérico.
        if any(term in field_text for term in ("phone", "telefone", "email", "e-mail")):
            return "contact"
        return "unknown"

    @staticmethod
    def _screen_key(text: str) -> str:
        text = unicodedata.normalize("NFKD", text.lower())
        return "".join(char for char in text if not unicodedata.combining(char))

    def _is_placeholder_option(self, text: str) -> bool:
        key = self._screen_key((text or "").strip())
        placeholders = ("select an option", "selecionar opcao", "selecione uma opcao", "choose an option")
        return not key or any(key.startswith(placeholder) for placeholder in placeholders)

    def _save_debug_html(self, step: int, title: str, reason: str, signals: dict = None) -> str:
        """Salva HTML sanitizado e metadados únicos da falha."""
        try:
            folder = save_failure_context(
                self.driver, f"etapa_{step}_{title}", reason, signals,
                selector="div[role='dialog'], .artdeco-modal__content, .jobs-easy-apply-modal",
            )
            self.status_queue.put(f"HTML de depuração salvo em: {folder}")
            return folder
        except Exception:
            self.status_queue.put("Falha ao salvar contexto HTML de depuração.")
            return ""

    def _is_application_sent(self) -> bool:
        try:
            modal_title = self.driver.find_element(*self.APPLICATION_SENT_MODAL)
            return "candidatura enviada" in modal_title.text.strip().lower()
        except NoSuchElementException:
            return False

    def _validate_current_form(self) -> list:
        """Valida campos obrigatórios e erros visíveis antes de avançar ou enviar."""
        errors = []
        seen = set()
        modal_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], .jobs-easy-apply-modal")
        scope = modal_elements[0] if modal_elements else self.driver
        for feedback in scope.find_elements(*self.VALIDATION_ERROR):
            try:
                if feedback.is_displayed() and feedback.text.strip():
                    seen.add("LinkedIn indica erro de validação.")
            except StaleElementReferenceException:
                continue

        controls = scope.find_elements(
            By.CSS_SELECTOR,
            "input[required], textarea[required], select[required], [aria-required='true']",
        )
        for field in controls:
            try:
                if not field.is_displayed():
                    continue
                field_type = (field.get_attribute("type") or field.tag_name or "").lower()
                name = field.get_attribute("name") or field.get_attribute("id") or "campo obrigatório"
                value = (field.get_attribute("value") or "").strip()
                if field_type in ("radio", "checkbox"):
                    peers = [
                        item for item in scope.find_elements(By.CSS_SELECTOR, "input")
                        if item.get_attribute("name") == field.get_attribute("name")
                    ]
                    valid = any(item.is_selected() for item in peers)
                elif field.tag_name.lower() == "select":
                    selected = Select(field).first_selected_option
                    valid = bool(selected.get_attribute("value") or selected.text.strip()) and not self._is_placeholder_option(selected.text)
                else:
                    valid = bool(value)
                if not valid:
                    seen.add(f"Campo obrigatório sem resposta: {name}.")
            except StaleElementReferenceException:
                seen.add("Um campo mudou durante a validação; tente novamente.")

        try:
            invalid = scope.find_elements(By.CSS_SELECTOR, ":invalid")
            if any(field.is_displayed() for field in invalid):
                seen.add("Há campo obrigatório ou inválido no formulário.")
        except StaleElementReferenceException:
            seen.add("O formulário mudou durante a validação; tente novamente.")
        errors.extend(sorted(seen))
        return errors

    def _require_valid_form(self) -> None:
        errors = self._validate_current_form()
        if errors:
            self.status_queue.put("Validação bloqueou o avanço: " + " ".join(errors))
            raise ValueError("Formulário contém campos obrigatórios ou erros de validação.")

    def _group_has_answer(self, group) -> bool:
        for locator in (
            (By.CSS_SELECTOR, "input[type='radio']:checked, input[type='checkbox']:checked"),
            (By.TAG_NAME, "select"),
        ):
            elements = group.find_elements(*locator)
            if elements:
                if locator[1] == "select":
                    selected = Select(elements[0]).first_selected_option
                    if not self._is_placeholder_option(selected.text):
                        return True
                else:
                    return True
        for field in group.find_elements(*self.TEXT_INPUTS):
            if (field.get_attribute("value") or "").strip():
                return True
        return False

    def _apply_group_answer(self, group, answer: str, options: list) -> bool:
        selects = group.find_elements(By.TAG_NAME, "select")
        if selects:
            Select(selects[0]).select_by_visible_text(answer)
            return self._screen_key(Select(selects[0]).first_selected_option.text.strip()) == self._screen_key(answer)

        text_fields = group.find_elements(*self.TEXT_INPUTS)
        if text_fields:
            field = text_fields[0]
            field.clear()
            field.send_keys(answer)
            return (field.get_attribute("value") or "").strip() == answer.strip()

        labels = group.find_elements(By.TAG_NAME, "label")
        for label in labels:
            if self._screen_key(label.text.strip()) == self._screen_key(answer):
                label.click()
                selected = group.find_elements(
                    By.CSS_SELECTOR, "input[type='radio']:checked, input[type='checkbox']:checked"
                )
                return bool(selected)
        return False

    def _handle_questions_screen(self):
        """Preenche uma pergunta por vez, verificando a resposta após cada interação."""
        def questions_or_progress_ready(driver):
            return (
                driver.find_elements(*self.FORM_GROUPS)
                or driver.find_elements(*self.NEXT_BUTTON)
                or driver.find_elements(*self.REVIEW_BUTTON)
            )

        WebDriverWait(self.driver, 2, poll_frequency=0.2).until(questions_or_progress_ready)
        for _ in range(15):
            self._check_control_signals()
            groups = self.driver.find_elements(*self.FORM_GROUPS)
            pending_group = None
            question_text = ""
            for group in groups:
                try:
                    if self._group_has_answer(group):
                        continue
                    question_element = next(
                        iter(group.find_elements(By.TAG_NAME, "legend") or group.find_elements(By.TAG_NAME, "label")),
                        None,
                    )
                    if question_element and question_element.text.strip():
                        pending_group = group
                        question_text = self._clean_question_text(question_element.text)
                        break
                except StaleElementReferenceException:
                    continue

            if pending_group is None:
                self.status_queue.put("Perguntas visíveis concluídas; validando campos obrigatórios.")
                self._require_valid_form()
                return True

            normalized_question = self._normalize_question(question_text)
            options = self._get_available_options(pending_group)
            cached_answer = self._cached_answer_for_question(question_text)
            answer = cached_answer if self._is_valid_cached_answer(question_text, cached_answer, options) else ""
            answered_by_ai = False
            if cached_answer and not answer:
                self.status_queue.put("Resposta salva ignorada porque não corresponde às opções atuais.")

            if not answer:
                ai_answer = self._ask_ai(question_text, options)
                answer = self._match_option(ai_answer, options) if options and ai_answer else ""
                answered_by_ai = bool(answer)

            if not answer:
                self.status_queue.put(f"USER_INPUT_REQUIRED|{question_text}")
                user_answer = self.answer_queue.get()
                if user_answer is None or user_answer.strip().lower() == "pular":
                    raise InterruptedError("Candidatura cancelada pelo usuário.")
                answer = self._match_option(user_answer, options) if options else ""
                if options and not answer:
                    self.status_queue.put("Resposta precisa corresponder exatamente a uma das opções visíveis.")
                    self.status_queue.put(f"USER_INPUT_REQUIRED|{question_text}")
                    user_answer = self.answer_queue.get()
                    if user_answer is None or user_answer.strip().lower() == "pular":
                        raise InterruptedError("Candidatura cancelada pelo usuário.")
                    answer = self._match_option(user_answer, options)
                if not options:
                    # Texto livre pode conter dados pessoais e depende do contexto da vaga;
                    # nunca o reaproveitamos automaticamente em outra candidatura.
                    answer = user_answer.strip()
                elif answer:
                    self.answers[normalized_question] = answer
                    self._save_answers()

            if not answer or not self._apply_group_answer(pending_group, answer, options):
                raise ValueError("A resposta não foi aplicada ou confirmada no campo.")
            self.status_queue.put(f"Resposta aplicada e conferida para: '{question_text}'.")
            if answered_by_ai:
                self._pause_after_ai_answer()
        raise ValueError("Limite de perguntas por etapa excedido.")

    def _handle_contact_step(self) -> str:
        self.status_queue.put("Processando: Informações de Contato.")
        self._handle_questions_screen()
        try:
            self._click_next_button()
            return "resume_or_optional"
        except TimeoutException:
            self._click_modal_button(self.REVIEW_BUTTON)
            return "review_or_questions"

    def _handle_resume_step(self) -> str:
        self.status_queue.put("Processando: Currículo.")
        try:
            self.driver.find_element(*self.SELECTED_RESUME_CARD)
        except NoSuchElementException:
            try:
                self._find_element(self.ANY_RESUME_CARD).find_element(*self.RESUME_CARD_LABEL).click()
                self.status_queue.put("Primeiro currículo da lista selecionado.")
            except (TimeoutException, NoSuchElementException):
                self.status_queue.put("AVISO: Nenhum card de currículo para selecionar.")
        self._require_valid_form()
        self._click_next_button()
        return "optional_or_questions"

    def _handle_questions_step(self) -> str:
        self.status_queue.put("Processando: Perguntas da etapa.")
        self._handle_questions_screen()
        self._require_valid_form()
        try:
            self._click_modal_button(self.REVIEW_BUTTON)
        except TimeoutException:
            self._click_next_button()
        return "review_or_questions"

    def _handle_optional_step(self) -> str:
        self.status_queue.put("Processando: Etapa opcional.")
        self._require_valid_form()
        self._click_optional_next()
        return "questions_or_review"

    def _handle_work_experience_step(self) -> str:
        self.status_queue.put("Processando: Experiência profissional.")
        self._require_valid_form()
        self._click_next_button()
        return "next_step"

    def _handle_review_step(self) -> str:
        self._require_valid_form()
        self.status_queue.put("Processando: Revisão. Enviando candidatura...")
        self._click_modal_button(self.SUBMIT_BUTTON)
        WebDriverWait(self.driver, 10, poll_frequency=0.2).until(lambda _: self._is_application_sent())
        self._click_modal_button(self.DONE_BUTTON)
        self.status_queue.put("Candidatura enviada com sucesso!")
        return "SUCCESS"

    def process_application(self, curriculum_path: str) -> str:
        """Executa cada etapa por um tratador próprio e registra a transição esperada."""
        handlers = {
            "contact": self._handle_contact_step,
            "resume": self._handle_resume_step,
            "questions": self._handle_questions_step,
            "optional": self._handle_optional_step,
            "work_experience": self._handle_work_experience_step,
            "review": self._handle_review_step,
        }
        allowed_transitions = {
            "contact": {"resume", "optional", "questions", "work_experience", "review"},
            "resume_or_optional": {"resume", "optional", "questions", "work_experience", "review"},
            "optional_or_questions": {"optional", "questions", "review"},
            "review_or_questions": {"review", "questions"},
            "questions_or_review": {"questions", "review"},
            "next_step": {"resume", "optional", "questions", "work_experience", "review"},
        }
        expected_transition = "início"
        for step in range(1, 11):
            self._check_control_signals()
            if self._is_application_sent():
                self.status_queue.put("Candidatura enviada com sucesso! Confirmando a tela final...")
                self._click_modal_button(self.DONE_BUTTON)
                return "SUCCESS"

            current_title = self._get_current_screen_title()
            signals = self._collect_screen_signals()
            state = self._classify_screen(current_title, signals)
            self.status_queue.put(f"[Etapa {step}] Tela: '{current_title}' (estado: {state})")
            if state == "unknown":
                self.status_queue.put("Tela não reconhecida. Salvando HTML e sinais do modal...")
                self._save_debug_html(step, current_title, "tela não reconhecida", signals)
                self.status_queue.put("ERRO: Sem transição segura para esta tela.")
                return "FAIL"

            if expected_transition != "início":
                self.status_queue.put(f"Transição esperada: {expected_transition}; detectada: {state}.")
                allowed_states = allowed_transitions.get(expected_transition)
                if allowed_states and state not in allowed_states:
                    self.status_queue.put("ERRO: Transição inesperada; candidatura interrompida para análise.")
                    self._save_debug_html(step, current_title, f"transição inesperada de {expected_transition} para {state}", signals)
                    return "FAIL"
            try:
                transition = handlers[state]()
                if transition == "SUCCESS":
                    return "SUCCESS"
                expected_transition = transition
            except Exception as error:
                self.status_queue.put(f"Falha na etapa '{state}': {sanitize_text(error)}")
                self._save_debug_html(step, current_title, f"falha na etapa {state}: {error}", signals)
                return "FAIL"

        self.status_queue.put("ERRO: Excedido o número máximo de etapas.")
        return "FAIL"
