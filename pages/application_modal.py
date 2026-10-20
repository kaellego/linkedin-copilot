# pages/application_modal.py
import time
import random
import threading
import json
import os
import re
import unicodedata
from pathlib import Path
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from pages.base_page import BasePage
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from services.ai_service import AIService
import config

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
    TEXT_INPUTS = (By.CSS_SELECTOR, "input:not([type='radio']):not([type='checkbox']), textarea")
    
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
        self.ai_service = AIService(api_key=getattr(config, "GEMINI_API_KEY", None))

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
            with open(config.ANSWERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.answers, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.status_queue.put(f"ERRO: Não foi possível salvar o arquivo de respostas: {e}")

    def _normalize_question(self, text: str) -> str:
        """Limpa o texto da pergunta para usar como chave de dicionário."""
        return text.replace('*', '').strip().lower()

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
        if not getattr(config, "GEMINI_API_KEY", None):
            return ""
        try:
            answer = self.ai_service.answer_question(question, options or None)
            if answer:
                self.status_queue.put("Resposta gerada pela API do Google Gemini.")
            return answer.strip()
        except Exception as e:
            self.status_queue.put(f"AVISO: API do Google indisponível: {e}")
            return ""

    def _match_option(self, answer: str, options: list) -> str:
        normalized_answer = answer.strip().lower()
        for option in options:
            if option.lower() == normalized_answer:
                return option
        for option in options:
            if normalized_answer in option.lower() or option.lower() in normalized_answer:
                return option
        return answer.strip()

    def _is_valid_cached_answer(self, question: str, answer: str, options: list) -> bool:
        normalized_question = self._normalize_question(question)
        normalized_answer = answer.strip().lower()
        if not normalized_answer or normalized_answer == normalized_question:
            return False
        if options:
            return any(option.lower() == normalized_answer for option in options)
        if normalized_question.startswith(("há quantos anos", "quantos anos", "quantos meses")):
            return normalized_answer.isdigit()
        return True

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
                    self.status_queue.put(f"Erro no keep-alive: {e}.")
                if self.stop_event.is_set():
                    raise InterruptedError("Sinal de parada recebido durante a pausa.")
            self.status_queue.put("Status: Retomando...")

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
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable(locator)
                )
                element.click()
                return
            except (TimeoutException, StaleElementReferenceException) as error:
                last_error = error
        raise TimeoutException(f"Botão de avanço da etapa opcional não encontrado: {last_error}")

    def _click_next_button(self):
        """Avança uma etapa usando o atributo atual ou o aria-label legado."""
        last_error = None
        for locator in (self.NEXT_BUTTON, self.NEXT_BUTTON_FALLBACK):
            try:
                element = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable(locator)
                )
                element.click()
                return
            except (TimeoutException, StaleElementReferenceException) as error:
                last_error = error
        raise TimeoutException(f"Botão 'Avançar' não encontrado: {last_error}")

    def _click_modal_button(self, locator, timeout: int = 4):
        element = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable(locator))
        element.click()

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
        dialog = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
        scope = dialog[0] if dialog else self.driver
        buttons = []
        for button in scope.find_elements(By.CSS_SELECTOR, "button"):
            label = (button.text or button.get_attribute("aria-label") or "").strip()
            if label:
                buttons.append(label)
        headings = [
            element.text.strip()
            for element in scope.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, [role='heading']")
            if element.text.strip()
        ]
        fields = []
        for field in scope.find_elements(By.CSS_SELECTOR, "input, textarea, select"):
            fields.append({
                "type": field.get_attribute("type") or field.tag_name,
                "name": field.get_attribute("name") or "",
                "id": field.get_attribute("id") or "",
                "label": field.get_attribute("aria-label") or field.get_attribute("placeholder") or "",
                "required": field.get_attribute("required") is not None,
            })
        groups = scope.find_elements(By.CSS_SELECTOR, ".fb-dash-form-element")
        return {
            "titulos": headings[:20],
            "botoes": buttons[:30],
            "campos": fields[:50],
            "quantidade_grupos_pergunta": len(groups),
            "tem_formulario": bool(scope.find_elements(By.CSS_SELECTOR, "form")),
            "tem_cartao_curriculo": bool(scope.find_elements(By.CSS_SELECTOR, ".jobs-document-upload-redesign-card__container")),
        }

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

    def _save_debug_html(self, step: int, title: str, reason: str, signals: dict = None) -> str:
        """Salva o DOM completo e o modal em um pacote legível por ocorrência."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", self._screen_key(title)).strip("_")[:40] or "unknown"
        folder = Path("debug_screenshots") / "html_debug" / f"{timestamp}_etapa_{step}_{safe_title}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            page_html = self.driver.page_source
            (folder / "pagina_completa.html").write_text(page_html, encoding="utf-8")
            modal_html = ""
            for selector in ("div[role='dialog']", ".artdeco-modal__content", ".jobs-easy-apply-modal"):
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    modal_html = elements[0].get_attribute("outerHTML") or ""
                    if modal_html:
                        break
            (folder / "modal.html").write_text(modal_html or "Modal não localizado no DOM.", encoding="utf-8")
            metadata = {
                "data_hora": time.strftime("%Y-%m-%d %H:%M:%S"),
                "etapa": step,
                "titulo_detectado": title,
                "motivo": reason,
                "sinais_detectados": signals or {},
                "url": self.driver.current_url,
                "arquivos": ["pagina_completa.html", "modal.html"],
            }
            (folder / "resumo.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status_queue.put(f"HTML de depuração salvo em: {folder}")
            return str(folder)
        except Exception as error:
            self.status_queue.put(f"Falha ao salvar HTML de depuração: {error}")
            return ""

    def _is_application_sent(self) -> bool:
        try:
            modal_title = self.driver.find_element(*self.APPLICATION_SENT_MODAL)
            return "candidatura enviada" in modal_title.text.strip().lower()
        except NoSuchElementException:
            return False

    def _handle_questions_screen(self):
        """
        Responde a perguntas adicionais usando o sistema de aprendizado.
        Atualizado para lidar com perguntas em <legend> e respostas em radio buttons.
        """
        # Adiciona um limite para evitar loops infinitos caso a lógica de saída falhe
        max_questions_to_answer = 15 
        for _ in range(max_questions_to_answer):
            self._check_control_signals()
            question_answered_in_this_loop = False
            
            try:
                # Aguarda um pouco para os elementos do formulário estarem disponíveis
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located(self.FORM_GROUPS)
                )
                form_groups = self.driver.find_elements(*self.FORM_GROUPS)

                for group in form_groups:
                    try:
                        # --- 1. LÓGICA ATUALIZADA PARA ENCONTRAR O TEXTO DA PERGUNTA ---
                        question_text = ""
                        try:
                            # Nova abordagem: a pergunta está em uma tag <legend>
                            question_element = group.find_element(By.TAG_NAME, "legend")
                            question_text = question_element.text
                        except NoSuchElementException:
                            # Abordagem antiga (fallback): a pergunta está em uma <label>
                            question_element = group.find_element(By.TAG_NAME, "label")
                            question_text = question_element.text
                        
                        if not question_text:
                            continue # Pula para o próximo grupo se não houver texto na pergunta

                        # Verifica se a pergunta já foi respondida (lógica de verificação de valor)
                        is_answered = False
                        try: # Verifica se é um select e já tem valor
                            select_el = group.find_element(By.TAG_NAME, "select")
                            if Select(select_el).first_selected_option.text not in ["", "Select an option", "Selecionar opção"]:
                                is_answered = True
                        except NoSuchElementException:
                            try: # Verifica se é um input de texto e já tem valor
                                input_el = group.find_element(*self.TEXT_INPUTS)
                                if input_el.get_attribute('value'):
                                    is_answered = True
                            except NoSuchElementException:
                                try: # Verifica se é um radio button e já está selecionado
                                    selected_radio = group.find_element(By.CSS_SELECTOR, "input[type='radio']:checked")
                                    is_answered = True
                                except NoSuchElementException:
                                    pass # Nenhuma das opções acima foi encontrada ou respondida
                        
                        if is_answered:
                            continue # Pula para a próxima pergunta

                        # --- Lógica de obter e aplicar a resposta (semelhante ao original) ---
                        normalized_question = self._normalize_question(question_text)
                        available_options = self._get_available_options(group)
                        answer_to_apply = self.answers.get(normalized_question)

                        if answer_to_apply and self._is_valid_cached_answer(
                            question_text, answer_to_apply, available_options
                        ):
                            self.status_queue.put("Resposta carregada do arquivo answers.json.")
                        else:
                            if answer_to_apply:
                                self.status_queue.put("AVISO: Resposta inválida no answers.json. Gerando nova resposta.")
                                answer_to_apply = ""
                            answer_to_apply = self._ask_ai(question_text, available_options)
                            if answer_to_apply and available_options:
                                answer_to_apply = self._match_option(answer_to_apply, available_options)
                            if answer_to_apply:
                                self.answers[normalized_question] = answer_to_apply
                                self._save_answers()
                                self.status_queue.put("Resposta da IA salva no arquivo answers.json.")

                        if not answer_to_apply:
                            self.status_queue.put(f"USER_INPUT_REQUIRED|{question_text}")
                            user_answer = self.answer_queue.get()
                            if user_answer is None or user_answer.lower() == 'pular':
                                raise InterruptedError("Candidatura cancelada pelo usuário.")
                            self.answers[normalized_question] = user_answer
                            self._save_answers()
                            answer_to_apply = user_answer
                        
                        # --- 2. LÓGICA ATUALIZADA PARA RESPONDER (SELECT, INPUT, RADIO) ---
                        try:
                            # Tenta responder como <select>
                            select_el = group.find_element(By.TAG_NAME, "select")
                            Select(select_el).select_by_visible_text(answer_to_apply)
                        except NoSuchElementException:
                            try:
                                # Tenta responder como <input> de texto ou <textarea>
                                input_el = group.find_element(*self.TEXT_INPUTS)
                                input_el.clear()
                                input_el.send_keys(answer_to_apply)
                            except NoSuchElementException:
                                try:
                                    # NOVA ABORDAGEM: Tenta responder clicando na label do radio/checkbox
                                    # XPath para encontrar uma label que contenha o texto da resposta
                                    answer_xpath = f".//label[normalize-space()='{answer_to_apply}']"
                                    answer_label = group.find_element(By.XPATH, answer_xpath)
                                    answer_label.click()
                                except NoSuchElementException:
                                    self.status_queue.put(
                                        f"ERRO: Campo de resposta não encontrado para: '{question_text}'"
                                    )
                                    raise NoSuchElementException(
                                        f"Campo de resposta não encontrado para: {question_text}"
                                    )
                        
                        self.status_queue.put(f"Respondido '{question_text}' com '{answer_to_apply}'.")
                        question_answered_in_this_loop = True
                        time.sleep(random.uniform(0.2, 0.5))
                        break # Sai do loop 'for group' para reavaliar a página do zero

                    except (NoSuchElementException, StaleElementReferenceException):
                        continue # Erro em um grupo específico, tenta o próximo
                
                # Se percorreu todas as perguntas e não respondeu nenhuma, significa que terminou
                if not question_answered_in_this_loop:
                    break # Sai do loop 'while True'

            except (TimeoutException, StaleElementReferenceException):
                self.status_queue.put("Modal de perguntas atualizado. Re-analisando...")
                continue # O DOM mudou, reinicia a análise
        
        self.status_queue.put("Todas as perguntas foram respondidas ou não foram encontradas novas perguntas.")

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
        self._click_next_button()
        return "optional_or_questions"

    def _handle_questions_step(self) -> str:
        self.status_queue.put("Processando: Perguntas da etapa.")
        self._handle_questions_screen()
        try:
            self._click_modal_button(self.REVIEW_BUTTON)
        except TimeoutException:
            self._click_next_button()
        return "review_or_questions"

    def _handle_optional_step(self) -> str:
        self.status_queue.put("Processando: Etapa opcional.")
        self._click_optional_next()
        return "questions_or_review"

    def _handle_work_experience_step(self) -> str:
        self.status_queue.put("Processando: Experiência profissional.")
        self._click_next_button()
        return "next_step"

    def _handle_review_step(self) -> str:
        self.status_queue.put("Processando: Revisão. Enviando candidatura...")
        self._click_modal_button(self.SUBMIT_BUTTON)
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
                self.status_queue.put(f"Falha na etapa '{state}': {error}")
                self._save_debug_html(step, current_title, f"falha na etapa {state}: {error}", signals)
                return "FAIL"

        self.status_queue.put("ERRO: Excedido o número máximo de etapas.")
        return "FAIL"
