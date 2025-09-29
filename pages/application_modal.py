# pages/application_modal.py
import time
import random
import threading
import json
import os
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from pages.base_page import BasePage
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import config

class ApplicationModal(BasePage):
    """
    Versão definitiva do modal, com a máquina de estados precisa para seguir
    o fluxo de 4 etapas: Contato -> Currículo -> Perguntas -> Revisão -> Envio.
    """
    
    # --- Locators ---
    MODAL_HEADER_TITLE = (By.CSS_SELECTOR, ".ph5 h3")
    MODAL_FALLBACK_TITLE = (By.CSS_SELECTOR, ".ph5 h4")
    WORK_EXPERIENCE_TITLE = (By.CSS_SELECTOR, "h3.t-16")
    FORM_GROUPS = (By.CSS_SELECTOR, ".fb-dash-form-element")
    
    # Botões de progresso específicos para cada etapa
    NEXT_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Avançar para próxima etapa']")
    REVIEW_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Revise sua candidatura']")
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Enviar candidatura']")
    
    DONE_BUTTON = (By.XPATH, "//button[contains(., 'Concluído')]")
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

    def _get_current_screen_title(self) -> str:
        """
        Identifica a tela atual do modal de forma robusta, testando múltiplos 
        seletores em ordem de prioridade.
        """
        # Lista de seletores para testar em ordem de importância
        title_locators = [
            self.MODAL_HEADER_TITLE,       # Seletor antigo principal (.ph5 h3)
            self.MODAL_FALLBACK_TITLE,     # Seletor antigo de fallback (.ph5 h4)
            self.WORK_EXPERIENCE_TITLE     # Novo seletor para "Work Experience" (h3.t-16)
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
        
        # Se o loop terminar e nenhum título for encontrado
        self.status_queue.put("ERRO: Nenhum seletor de título conhecido foi encontrado no modal.")
        return "unknown"

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
                                input_el = group.find_element(By.CSS_SELECTOR, "input[type='text'], textarea")
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
                        answer_to_apply = self.answers.get(normalized_question)

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
                                input_el = group.find_element(By.CSS_SELECTOR, "input[type='text'], textarea")
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
                                    self.status_queue.put(f"AVISO: Campo de resposta não encontrado para: '{question_text}'")
                                    continue
                        
                        self.status_queue.put(f"Respondido '{question_text}' com '{answer_to_apply}'.")
                        question_answered_in_this_loop = True
                        time.sleep(random.uniform(1.2, 1.8))
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

    def process_application(self, curriculum_path: str) -> str:
        """Executa a candidatura usando uma máquina de estados explícita."""
        max_steps = 10
        for step in range(max_steps):
            self._check_control_signals()
            time.sleep(2)
            
            current_title = self._get_current_screen_title()
            self.status_queue.put(f"[Etapa {step + 1}] Tela atual: '{current_title}'")

            try:
                # --- MÁQUINA DE ESTADOS ---
                if "informações de contato" in current_title:
                    self.status_queue.put("Processando: Informações de Contato. Clicando para avançar ou enviar...")
                    try:
                        # Tenta clicar no botão 'próximo' primeiro
                        self._click(self.NEXT_BUTTON)
                    except Exception as e:
                        # Se o primeiro botão não for encontrado ou falhar, tenta o segundo
                        print(f"Não foi possível clicar em NEXT_BUTTON ({e}), tentando SUBMIT_BUTTON.")
                        try:
                            self._click(self.SUBMIT_BUTTON)
                        except Exception as e2:
                            # Se ambos falharem, você pode registrar um erro mais específico
                            error_message = "ERRO: Nenhum dos botões (NEXT_BUTTON ou SUBMIT_BUTTON) foi encontrado."
                            self.status_queue.put(error_message)
                            print(f"{error_message} Detalhes: {e2}")
                            # Opcional: relançar a exceção se a automação não puder continuar
                            # raise e2
                
                elif "resume" in current_title:
                    self.status_queue.put("Processando: Resume. Clicando em Avançar...")
                    self._click(self.NEXT_BUTTON)

                elif "currículo" in current_title:
                    self.status_queue.put("Processando: Currículo...")
                    try:
                        self.driver.find_element(*self.SELECTED_RESUME_CARD)
                    except NoSuchElementException:
                        try:
                            self._find_element(self.ANY_RESUME_CARD).find_element(*self.RESUME_CARD_LABEL).click()
                            self.status_queue.put("Primeiro currículo da lista selecionado.")
                        except (TimeoutException, NoSuchElementException):
                            self.status_queue.put("AVISO: Nenhum card de currículo para selecionar.")
                    self._click(self.NEXT_BUTTON)

                elif "work experience" in current_title:
                    self.status_queue.put("Processando: Work Experience. Clicando em Avançar...")
                    self._click(self.NEXT_BUTTON)

                elif "marque esta vaga como preferencial" in current_title:
                    self.status_queue.put("Processando: Tela opcional de 'Vaga Preferencial'. Clicando para avançar...")
                    # A ação é a mesma da tela de contato: apenas avançar.
                    # Usamos o mesmo try/except para clicar no botão que estiver disponível.
                    try:
                        self._click(self.NEXT_BUTTON)
                    except Exception:
                        self._click(self.REVIEW_BUTTON) # Pode ser o botão de revisar também
                
                elif "perguntas adicionais" in current_title:
                    self.status_queue.put("Processando: Perguntas Adicionais...")
                    self._handle_questions_screen()
                    self._click(self.REVIEW_BUTTON)

                elif "additional questions" in current_title:
                    self.status_queue.put("Processando: Perguntas Adicionais...")
                    self._handle_questions_screen()
                    self._click(self.REVIEW_BUTTON)

                elif "home address" in current_title:
                    self.status_queue.put("Processando: Home address...")
                    self._handle_questions_screen()
                    self._click(self.NEXT_BUTTON)

                elif "revise sua candidatura" in current_title:
                    self.status_queue.put("Processando: Revisar Candidatura. Clicando em Enviar...")
                    self._click(self.SUBMIT_BUTTON)
                    self._click(self.DONE_BUTTON)
                    self.status_queue.put("Candidatura enviada com sucesso!")
                    return "SUCCESS"
                
                else:
                    # Lógica para formulários de 1 passo que vão direto para a tela de Revisão/Envio
                    try:
                        self.status_queue.put(f"Tela desconhecida '{current_title}'. Verificando se é a tela final...")
                        self._click(self.SUBMIT_BUTTON)
                        self._click(self.DONE_BUTTON)
                        return "SUCCESS"
                    except TimeoutException:
                        self.status_queue.put(f"ERRO: Não foi possível identificar a tela ou encontrar uma ação.")
                        return "FAIL"

                time.sleep(2) # Pausa pós-clique para a próxima tela estabilizar

            except TimeoutException:
                self.status_queue.put(f"ERRO: O botão de progresso não foi encontrado na tela '{current_title}'.")
                try:
                    modal_html = self.driver.find_element(By.CSS_SELECTOR, ".artdeco-modal__content").get_attribute('outerHTML')
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    filename = f"debug_screenshots/modal_fail_html_{timestamp}.txt"
                    with open(filename, "w", encoding="utf-8") as f: f.write(modal_html)
                    self.status_queue.put(f"HTML do modal salvo em: {filename}")
                except Exception as e:
                    self.status_queue.put(f"Falha ao salvar HTML de depuração: {e}")
                return "FAIL"
            except Exception as e:
                self.status_queue.put(f"Erro inesperado na etapa {step+1}: {e}")
                return "FAIL"

        self.status_queue.put("ERRO: Excedido o número máximo de etapas.")
        return "FAIL"