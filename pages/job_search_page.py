# pages/job_search_page.py
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
from pages.application_modal import ApplicationModal
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import config

class JobSearchPage(BasePage):
    """
    Versão final e completa. Gerencia a busca, filtragem (incluindo histórico de vagas),
    paginação e delega a candidatura para a classe ApplicationModal.
    """
    
    # --- Locators ---
    JOB_LIST_ITEM = (By.CSS_SELECTOR, "li[data-occludable-job-id]")
    JOB_TITLE_LINK = (By.CSS_SELECTOR, "a.job-card-container__link")
    JOB_LOCATION_TEXT = (By.CSS_SELECTOR, "div.artdeco-entity-lockup__caption span[dir='ltr']")
    APPLIED_INDICATOR = (By.CSS_SELECTOR, ".job-card-container__footer-job-state")
    APPLY_BUTTON = (By.CSS_SELECTOR, "button.jobs-apply-button")
    EASY_APPLY_TAG = (By.XPATH, ".//*[contains(text(), 'Candidatura simplificada')]")
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
        self.applied_job_ids = self._load_applied_jobs()

    def _load_answers(self) -> dict:
        """Carrega o arquivo de respostas conhecidas."""
        if os.path.exists(config.ANSWERS_FILE):
            try:
                with open(config.ANSWERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.status_queue.put(f"AVISO: Não foi possível carregar o arquivo de respostas: {e}")
                return {}
        return {}

    def _load_applied_jobs(self) -> list:
        """Carrega a lista de IDs de vagas já aplicadas do arquivo JSON."""
        self.status_queue.put("Carregando histórico de vagas aplicadas...")
        if os.path.exists(config.APPLIED_JOBS_FILE):
            try:
                with open(config.APPLIED_JOBS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                self.status_queue.put(f"AVISO: Não foi possível carregar o histórico: {config.APPLIED_JOBS_FILE}")
                return []
        return []

    def _save_applied_job(self, job_id: str):
        """Adiciona um novo ID à lista e salva no arquivo JSON."""
        if job_id and job_id not in self.applied_job_ids:
            self.applied_job_ids.append(job_id)
            try:
                with open(config.APPLIED_JOBS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.applied_job_ids, f, indent=4)
                self.status_queue.put(f"Vaga {job_id} salva no histórico.")
            except IOError as e:
                self.status_queue.put(f"ERRO: Não foi possível salvar o histórico: {e}")

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

    def search_jobs(self, keywords: str, location: str, base_url: str, easy_apply_mode: bool = True):
        """Navega para a URL de busca, aplicando o filtro de candidatura simplificada se ativo."""
        filter_param = "true" if easy_apply_mode else "false"
        mode_text = "Simplificada" if easy_apply_mode else "Normal"
        self.status_queue.put(f"Buscando vagas para '{keywords}' em modo de Candidatura {mode_text}.")
        url = f"{base_url}?keywords={keywords.replace(' ', '%20')}&location={location}&f_AL={filter_param}"
        self.open_url(url)
    
    def _get_job_count(self) -> int:
        """Espera a lista carregar e rola a página exaustivamente para carregar todas as vagas."""
        try:
            self.status_queue.put("Aguardando o carregamento inicial da lista de vagas...")
            self.wait.until(EC.visibility_of_element_located(self.JOB_LIST_ITEM))
            
            self.status_queue.put("Iniciando rolagem para carregar todas as vagas da página...")
            last_count = 0
            attempts = 0
            while attempts < 5:
                self._check_control_signals()
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                current_count = len(self.driver.find_elements(*self.JOB_LIST_ITEM))
                if current_count == last_count:
                    attempts += 1
                else:
                    last_count = current_count
                    attempts = 0
                self.status_queue.put(f"Carregadas {last_count} vagas até o momento...")

            self.status_queue.put(f"Rolagem finalizada. Encontradas {last_count} vagas REAIS na página.")
            return last_count
        except TimeoutException:
            self.status_queue.put("ERRO: A lista de vagas não carregou em 20 segundos.")
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            screenshot_path = f'debug_screenshots/vagas_nao_carregadas_{timestamp}.png'
            self.driver.save_screenshot(screenshot_path)
            self.status_queue.put(f"Screenshot salvo em: {screenshot_path}")
            return 0
            
    def process_easy_apply_jobs(self, curriculum_path: str) -> str:
        """Processa vagas no modo 'Candidatura Simplificada'."""
        job_count = self._get_job_count()
        if job_count == 0: return "FAIL"
            
        for i in range(job_count):
            self._check_control_signals()
            self.status_queue.put(f"--- Verificando vaga {i + 1} de {job_count} ---")
            
            original_style = None
            job = None
            try:
                all_jobs = self.driver.find_elements(*self.JOB_LIST_ITEM)
                if i >= len(all_jobs): break
                job = all_jobs[i]

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", job)
                time.sleep(0.5)
                original_style = self._highlight_element(job)
                time.sleep(0.5)

                job_id = job.get_attribute('data-occludable-job-id')
                if job_id in self.applied_job_ids:
                    self.status_queue.put(f"Vaga {job_id} já está no histórico. Pulando...")
                    continue
                
                try:
                    applied_indicator = job.find_element(*self.APPLIED_INDICATOR)
                    if "candidatou-se" in applied_indicator.text.lower():
                        self.status_queue.put(f"Vaga já marcada como candidatada na página. Pulando...")
                        continue
                except NoSuchElementException: pass

                location_element = job.find_element(*self.JOB_LOCATION_TEXT)
                location_text = location_element.text.lower()
                if not any(keyword in location_text for keyword in config.LOCATIONS_KEYWORDS):
                    self.status_queue.put(f"Pulando vaga. Localização '{location_element.text}' não corresponde ao filtro.")
                    continue
                
                self.status_queue.put(f"Localização OK: '{location_element.text}'. Processando candidatura...")

                modal_is_open = False
                try:
                    job.click()
                    self.wait.until(EC.element_to_be_clickable(self.APPLY_BUTTON)).click()
                    modal_is_open = True
                    
                    application_modal = ApplicationModal(self.driver, self.status_queue, self.answer_queue, self.pause_event, self.stop_event, self.answers)
                    status = application_modal.process_application(curriculum_path)
                    
                    if status == "SUCCESS":
                        self._save_applied_job(job_id)
                        return "PAGE_RELOADED"
                    if status == "LIMIT_REACHED": return "LIMIT_REACHED"
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
                            time.sleep(2) 
                            close_button = self.wait.until(EC.element_to_be_clickable(self.CLOSE_MODAL_BUTTON))
                            close_button.click()
                            time.sleep(1)
                            try:
                                discard_button = self.driver.find_element(*self.DISCARD_BUTTON)
                                if discard_button.is_displayed():
                                    discard_button.click()
                                    self.status_queue.put("Confirmação de descarte clicada.")
                            except (NoSuchElementException, TimeoutException): pass 
                        except Exception:
                            self.status_queue.put("Modal provavelmente fechou automaticamente.")
            
            except (NoSuchElementException, StaleElementReferenceException) as e:
                self.status_queue.put(f"Item {i+1} não é uma vaga padrão ou está 'stale' ({e.__class__.__name__}). Pulando.")
            
            finally:
                if job and original_style is not None:
                    try: self._unhighlight_element(job, original_style)
                    except StaleElementReferenceException: pass

        return "PROCESSED"

    def process_normal_jobs(self):
        job_count = self._get_job_count()
        if job_count == 0: return

        main_window = self.driver.current_window_handle
        for i in range(job_count):
            self._check_control_signals()
            self.status_queue.put(f"--- Verificando vaga {i + 1} de {job_count} ---")

            original_style = None
            job = None
            try:
                all_jobs = self.driver.find_elements(*self.JOB_LIST_ITEM)
                if i >= len(all_jobs): break
                job = all_jobs[i]

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", job)
                time.sleep(0.5)
                original_style = self._highlight_element(job)
                time.sleep(0.5)

                job_id = job.get_attribute('data-occludable-job-id')
                if job_id in self.applied_job_ids:
                    self.status_queue.put(f"Vaga {job_id} já está no histórico. Pulando...")
                    continue
                
                try:
                    applied_indicator = job.find_element(*self.APPLIED_INDICATOR)
                    if "candidatou-se" in applied_indicator.text.lower():
                        self.status_queue.put("Vaga já candidatada na página. Pulando...")
                        continue
                except NoSuchElementException: pass

                location_element = job.find_element(*self.JOB_LOCATION_TEXT)
                location_text = location_element.text.lower()
                if not any(keyword in location_text for keyword in config.LOCATIONS_KEYWORDS):
                    self.status_queue.put(f"Pulando vaga. Localização '{location_element.text}' não corresponde ao filtro.")
                    continue
                
                self.status_queue.put(f"Localização OK: '{location_element.text}'.")

                try:
                    job.find_element(*self.EASY_APPLY_TAG)
                    self.status_queue.put("Vaga simplificada encontrada. Pulando no modo de busca normal.")
                    continue
                except NoSuchElementException:
                    try:
                        job_link_element = job.find_element(*self.JOB_TITLE_LINK)
                        job_url = job_link_element.get_attribute('href')
                        self.status_queue.put("VAGA NORMAL: Abrindo em nova aba para candidatura manual...")
                        self.driver.switch_to.new_window('tab')
                        self.driver.get(job_url)
                        time.sleep(2)
                        self.driver.switch_to.window(main_window)
                        time.sleep(1)
                    except Exception as e:
                        self.status_queue.put(f"Não foi possível abrir a vaga normal em nova aba: {e}")
                
            except (NoSuchElementException, StaleElementReferenceException) as e:
                self.status_queue.put(f"Item {i+1} não é uma vaga padrão ou está 'stale' ({e.__class__.__name__}). Pulando.")
            
            finally:
                if job and original_style is not None:
                    try: self._unhighlight_element(job, original_style)
                    except StaleElementReferenceException: pass

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