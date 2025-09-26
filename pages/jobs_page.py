# pages/jobs_page.py
import time
import random
import threading
import json
import os
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
from pages.base_page import BasePage
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import config

class JobsPage(BasePage):
    """
    Versão final da página de vagas, otimizada para velocidade e confiabilidade,
    removendo pausas fixas e melhorando a espera da paginação.
    """
    
    # --- Locators ---
    JOB_LIST_ITEM = (By.CSS_SELECTOR, "li[data-occludable-job-id]")
    JOB_LOCATION_TEXT = (By.CSS_SELECTOR, "div.artdeco-entity-lockup__caption span[dir='ltr']")
    APPLIED_INDICATOR = (By.CSS_SELECTOR, ".job-card-container__footer-job-state")
    APPLY_BUTTON = (By.CSS_SELECTOR, "button.jobs-apply-button")
    
    # Locators do Modal
    MODAL_CONTENT = (By.CSS_SELECTOR, ".jobs-easy-apply-modal__content")
    FORM_GROUPS = (By.CSS_SELECTOR, ".fb-dash-form-element")
    NEXT_BUTTON = (By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
    REVIEW_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Revise sua candidatura']")
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Enviar candidatura']")
    UPLOAD_INPUT = (By.CSS_SELECTOR, 'input[type="file"]')
    CLOSE_MODAL_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Fechar']")
    DISCARD_BUTTON = (By.CSS_SELECTOR, "button[data-control-name='discard_application_confirm_btn']")
    NEXT_PAGE_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Ver próxima página']")

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event):
        super().__init__(driver)
        self.status_queue = status_queue
        self.answer_queue = answer_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.answers = self._load_answers()

    def _load_answers(self) -> dict:
        if os.path.exists(config.ANSWERS_FILE):
            try:
                with open(config.ANSWERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.status_queue.put(f"AVISO: Não foi possível carregar o arquivo de respostas: {e}")
                return {}
        return {}

    def _save_answers(self):
        try:
            with open(config.ANSWERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.answers, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.status_queue.put(f"ERRO: Não foi possível salvar o arquivo de respostas: {e}")

    def _normalize_question(self, text: str) -> str:
        return text.replace('*', '').strip().lower()

    def _check_control_signals(self):
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

    def search_jobs(self, keywords: str, location: str, base_url: str):
        self.status_queue.put(f"Buscando vagas para '{keywords}' em '{location}'.")
        url = f"{base_url}?keywords={keywords.replace(' ', '%20')}&location={location}&f_AL=true"
        self.open_url(url)
    
    def _handle_application_modal(self, curriculum_path: str) -> bool:
        max_steps = 7
        for step in range(max_steps):
            self._check_control_signals()
            # MODIFICADO: Removido o sleep fixo, agora esperamos por elementos.
            self.wait.until(EC.presence_of_element_located(self.MODAL_CONTENT))

            try:
                form_groups = self.driver.find_elements(*self.FORM_GROUPS)
                for group in form_groups:
                    try:
                        label = group.find_element(By.TAG_NAME, "label")
                        question_text = label.text
                        if not question_text: continue
                        normalized_question = self._normalize_question(question_text)
                        
                        answer_to_apply = None
                        if normalized_question in self.answers:
                            answer_to_apply = self.answers[normalized_question]
                            self.status_queue.put(f"Usando resposta conhecida para: '{question_text}'")
                        else:
                            self.status_queue.put(f"USER_INPUT_REQUIRED|{question_text}")
                            user_answer = self.answer_queue.get()
                            if user_answer is None or user_answer.lower() == 'pular':
                                self.status_queue.put("Cancelando candidatura.")
                                return False
                            self.answers[normalized_question] = user_answer
                            self._save_answers()
                            answer_to_apply = user_answer
                        if answer_to_apply is not None:
                            try:
                                select_el = group.find_element(By.TAG_NAME, "select")
                                Select(select_el).select_by_visible_text(answer_to_apply)
                                self.status_queue.put(f"Selecionado '{answer_to_apply}'.")
                            except NoSuchElementException:
                                input_el = group.find_element(By.TAG_NAME, "input")
                                if input_el.get_attribute('value') == '':
                                    input_el.send_keys(answer_to_apply)
                                    self.status_queue.put(f"Preenchido '{answer_to_apply}'.")
                    except NoSuchElementException: continue
            except Exception as e:
                self.status_queue.put(f"Erro ao processar perguntas: {e}")

            try:
                upload_field = self.driver.find_element(*self.UPLOAD_INPUT)
                if upload_field.is_displayed():
                    upload_field.send_keys(curriculum_path)
            except NoSuchElementException: pass

            try:
                self._click(self.SUBMIT_BUTTON)
                self.status_queue.put("Candidatura enviada com sucesso!")
                # Espera a confirmação de "Candidatura enviada" aparecer antes de retornar
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Candidatura enviada')]")))
                return True
            except TimeoutException:
                self.status_queue.put(f"Etapa {step + 1}: Procurando 'Revisar' ou 'Avançar'...")
                try:
                    self._click(self.REVIEW_BUTTON)
                    self.status_queue.put("Indo para a tela de revisão...")
                    continue
                except TimeoutException:
                    try:
                        self._click(self.NEXT_BUTTON)
                        self.status_queue.put("Avançando para a próxima etapa.")
                        continue
                    except TimeoutException:
                        self.status_queue.put("ERRO: Não foi possível encontrar 'Enviar', 'Revisar' ou 'Avançar'.")
                        return False
        
        self.status_queue.put("ERRO: Excedido o número máximo de etapas.")
        return False

    def apply_to_jobs_on_page(self, curriculum_path: str) -> bool:
        try:
            self.status_queue.put("Aguardando o carregamento da lista de vagas...")
            self.wait.until(EC.visibility_of_element_located(self.JOB_LIST_ITEM))
            self.status_queue.put("Lista de vagas carregada.")
            self.status_queue.put("Rolando a página para carregar mais vagas...")
            for _ in range(3): 
                self._check_control_signals()
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1) # Pequena pausa para o scroll renderizar
            job_count = len(self.driver.find_elements(*self.JOB_LIST_ITEM))
            self.status_queue.put(f"Encontradas {job_count} vagas REAIS na página.")
        except TimeoutException:
            self.status_queue.put("ERRO: A lista de vagas não carregou em 20 segundos.")
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            screenshot_path = f'debug_screenshots/vagas_nao_carregadas_{timestamp}.png'
            self.driver.save_screenshot(screenshot_path)
            self.status_queue.put(f"Screenshot salvo em: {screenshot_path}")
            return False
            
        for i in range(job_count):
            self._check_control_signals()
            self.status_queue.put(f"--- Verificando vaga {i + 1} de {job_count} ---")
            
            try:
                all_jobs = self.driver.find_elements(*self.JOB_LIST_ITEM)
                if i >= len(all_jobs):
                    self.status_queue.put("A lista de vagas mudou. Interrompendo página.")
                    break
                job = all_jobs[i]

                try:
                    applied_indicator = job.find_element(*self.APPLIED_INDICATOR)
                    if "candidatou-se" in applied_indicator.text.lower():
                        self.status_queue.put("Vaga já candidatada. Pulando...")
                        continue
                except NoSuchElementException:
                    pass

                location_element = job.find_element(*self.JOB_LOCATION_TEXT)
                location_text = location_element.text.lower()
                
                if not any(keyword in location_text for keyword in config.LOCATIONS_KEYWORDS):
                    self.status_queue.put(f"Pulando vaga. Localização '{location_element.text}' não corresponde ao filtro.")
                    continue

                self.status_queue.put(f"Localização OK: '{location_element.text}'. Processando...")

            except (NoSuchElementException, StaleElementReferenceException) as e:
                self.status_queue.put(f"Item {i+1} não é uma vaga padrão ou está 'stale' ({e.__class__.__name__}). Pulando.")
                continue
            
            modal_is_open = False
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job)
                time.sleep(0.5) # Pequena pausa para o scroll
                job.click()
                self.wait.until(EC.element_to_be_clickable(self.APPLY_BUTTON)).click()
                modal_is_open = True
                
                success = self._handle_application_modal(curriculum_path)
                
                if success:
                    return True
                else:
                    self.status_queue.put("Candidatura falhou ou foi pulada.")
            
            except InterruptedError as e:
                self.status_queue.put(str(e))
                break 
            except Exception as e:
                self.status_queue.put(f"ERRO ao processar vaga: {e}.")
            
            finally:
                if modal_is_open:
                    self.status_queue.put("Fechando modal de candidatura...")
                    try:
                        close_button = self.wait.until(EC.element_to_be_clickable(self.CLOSE_MODAL_BUTTON))
                        close_button.click()
                        time.sleep(1) # Pausa para o modal começar a fechar
                        try:
                            discard_button = self.driver.find_element(*self.DISCARD_BUTTON)
                            if discard_button.is_displayed():
                                discard_button.click()
                        except (NoSuchElementException, TimeoutException):
                            pass 
                    except Exception:
                        self.status_queue.put("Modal provavelmente fechou automaticamente.")
        return False

    def go_to_next_page(self) -> bool:
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            next_button = self._find_element(self.NEXT_PAGE_BUTTON)
            if next_button.get_attribute("disabled"):
                self.status_queue.put("Botão 'Avançar' desabilitado. Fim da paginação.")
                return False
            first_job_on_current_page = self._find_element(self.JOB_LIST_ITEM)
            self.status_queue.put("Clicando em 'Avançar'...")
            self.driver.execute_script("arguments[0].click();", next_button)
            
            # ESPERA DUPLA: Espera o conteúdo antigo sumir E o novo aparecer.
            self.status_queue.put("Aguardando nova página carregar...")
            self.wait.until(EC.staleness_of(first_job_on_current_page))
            self.wait.until(EC.visibility_of_element_located(self.JOB_LIST_ITEM))
            self.status_queue.put("Nova página carregada.")
            
            return True

        except (TimeoutException, NoSuchElementException):
            self.status_queue.put("Botão 'Avançar' não encontrado. Fim dos resultados.")
            return False
        except Exception as e:
            self.status_queue.put(f"Erro ao mudar de página: {e}")
            return False