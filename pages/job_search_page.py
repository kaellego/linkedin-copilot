# pages/job_search_page.py
import time
import random
import threading
import json
import os
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from pages.base_page import BasePage
from pages.application_modal import ApplicationModal
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
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
    EXTERNAL_APPLY_BUTTON = (By.CSS_SELECTOR, "button[data-live-test-job-apply-button][role='link']")
    EXTERNAL_APPLY_BUTTON_FALLBACK = (By.CSS_SELECTOR, "button.jobs-apply-button[aria-label^='Candidatar-se']")
    EXTERNAL_APPLY_BUTTON_GENERIC = (By.CSS_SELECTOR, "button.jobs-apply-button[data-live-test-job-apply-button]")
    EXTERNAL_APPLY_BUTTON_TEXT = (By.XPATH, "//button[contains(@aria-label, 'Candidatar-se') or .//span[contains(normalize-space(), 'Candidatar-se')]]")
    EXTERNAL_CONTINUE_BUTTON = (By.CSS_SELECTOR, "div[data-test-modal][aria-labelledby='jobs-apply-starter'] button[data-live-test-job-apply-button]")
    EXTERNAL_CONTINUE_BUTTON_FALLBACK = (By.XPATH, "//div[@aria-labelledby='jobs-apply-starter']//button[contains(normalize-space(.), 'Continuar')]")
    OFFSITE_APPLY_CONFIRMATION_YES = (By.CSS_SELECTOR, "button[data-view-name='offsite-apply-confirmation-banner-reply-yes']")
    EASY_APPLY_TAG = (By.XPATH, ".//*[contains(., 'Candidatura simplificada')]")
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
        self.location_keywords = config.LOCATIONS_KEYWORDS
        self.work_type = "Todas"

    def _matches_work_type(self, location_text: str) -> bool:
        """Confere a modalidade exibida no card da vaga."""
        if self.work_type == "Todas":
            return True

        normalized_text = unicodedata.normalize("NFKD", location_text).encode("ascii", "ignore").decode().lower()
        markers = {
            "Presencial": ("presencial", "on-site", "onsite", "on site"),
            "Híbrida": ("hibrid", "hybrid"),
            "Remota": ("remot", "remote"),
        }
        return any(marker in normalized_text for marker in markers.get(self.work_type, ()))

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

    def _wait_for_external_tab_close(self, external_window: str, main_window: str):
        """Aguarda o fechamento da aba externa e retorna à aba de resultados."""
        self.status_queue.put("Monitorando a aba externa. Feche-a para continuar automaticamente...")
        while external_window in self.driver.window_handles:
            if self.stop_event.is_set():
                raise InterruptedError("Sinal de parada recebido durante a candidatura externa.")
            try:
                self.driver.switch_to.window(external_window)
                _ = self.driver.current_url
            except Exception:
                pass
            time.sleep(1)

        if main_window in self.driver.window_handles:
            self.driver.switch_to.window(main_window)
        self.pause_event.set()
        self.status_queue.put("Aba externa fechada. Retomando automaticamente...")

    def _confirm_offsite_application(self):
        """Confirma a candidatura externa quando o LinkedIn exibe o banner."""
        try:
            confirm_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(self.OFFSITE_APPLY_CONFIRMATION_YES)
            )
            confirm_button.click()
            self.status_queue.put("Confirmação de candidatura externa encontrada. Botão 'Sim' clicado.")
        except TimeoutException:
            pass

    def _find_clickable_element(self, locator, timeout: int):
        """Encontra um botão visível sem avaliar um elemento nulo durante atualizações do DOM."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                elements = self.driver.find_elements(*locator)
            except WebDriverException:
                return None
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        return element
                except StaleElementReferenceException:
                    continue
                except WebDriverException:
                    return None
            time.sleep(0.5)
        return None

    def _canonical_job_url(self, job_url: str) -> str:
        """Remove parâmetros temporários do LinkedIn e mantém apenas a URL da vaga."""
        absolute_url = urljoin(self.driver.current_url, job_url)
        parts = urlsplit(absolute_url)
        if parts.path.startswith("/jobs/view/"):
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        return absolute_url

    def _click_external_apply_button(self, element):
        """Clica no botão externo e usa JavaScript se o layout bloquear o clique nativo."""
        try:
            element.click()
        except WebDriverException:
            self.driver.execute_script("arguments[0].click();", element)

    def _restore_main_window(self, main_window: str):
        """Retorna para a janela principal ou para a primeira janela ainda válida."""
        handles = self.driver.window_handles
        if main_window in handles:
            self.driver.switch_to.window(main_window)
        elif handles:
            self.driver.switch_to.window(handles[0])
        self.pause_event.set()

    def search_jobs(self, keywords: str, location: str, base_url: str, easy_apply_mode: bool = True, work_type: str = "Todas"):
        """Navega para a URL de busca, aplicando o filtro de candidatura simplificada se ativo."""
        mode_text = "Simplificada" if easy_apply_mode else "Normal"
        work_type = work_type.strip() if isinstance(work_type, str) else "Todas"
        work_type_params = {"Presencial": "1", "Remota": "2", "Híbrida": "3"}
        work_type_param = work_type_params.get(work_type)
        self.work_type = work_type if work_type in work_type_params else "Todas"
        self.location_keywords = [
            term.strip().lower()
            for term in location.split(",")
            if term.strip()
        ]
        self.status_queue.put(f"Buscando vagas para '{keywords}' em modo de Candidatura {mode_text}.")
        query_params = {
            "keywords": keywords,
            "location": location,
        }
        if easy_apply_mode:
            query_params["f_AL"] = "true"
        if work_type_param:
            query_params["f_WT"] = work_type_param
        base_url_parts = urlsplit(base_url)
        base_query = [
            (key, value)
            for key, value in parse_qsl(base_url_parts.query, keep_blank_values=True)
            if key.lower() != "f_wt"
        ]
        base_query.extend(query_params.items())
        url = urlunsplit((
            base_url_parts.scheme,
            base_url_parts.netloc,
            base_url_parts.path,
            urlencode(base_query),
            base_url_parts.fragment,
        ))
        self.status_queue.put(f"URL da busca: {url}")
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
                time.sleep(1)
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
            
    def process_easy_apply_jobs(self, curriculum_path: str, process_normal_jobs: bool = False) -> str:
        """Processa simplificadas e pode iniciar imediatamente a etapa de links."""
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
                time.sleep(0.2)
                original_style = self._highlight_element(job)
                time.sleep(0.2)

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

                try:
                    job.find_element(*self.EASY_APPLY_TAG)
                except NoSuchElementException:
                    if process_normal_jobs:
                        self.status_queue.put("Vaga normal encontrada. Abrindo imediatamente a candidatura por link...")
                        self.process_normal_jobs()
                        return "NORMAL_PROCESSED"
                    self.status_queue.put("Vaga normal reservada para a etapa de candidatura por link.")
                    continue

                location_element = job.find_element(*self.JOB_LOCATION_TEXT)
                location_text = location_element.text.lower()
                if self.location_keywords and not any(keyword in location_text for keyword in self.location_keywords):
                    self.status_queue.put(f"Pulando vaga. Localização '{location_element.text}' não corresponde ao filtro.")
                    continue
                if not self._matches_work_type(location_text):
                    self.status_queue.put(f"Pulando vaga. Modalidade '{location_element.text}' não corresponde ao filtro '{self.work_type}'.")
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
                        modal_is_open = False
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
                            time.sleep(0.5) 
                            close_button = self.wait.until(EC.element_to_be_clickable(self.CLOSE_MODAL_BUTTON))
                            close_button.click()
                            time.sleep(0.3)
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
                if self.location_keywords and not any(keyword in location_text for keyword in self.location_keywords):
                    self.status_queue.put(f"Pulando vaga. Localização '{location_element.text}' não corresponde ao filtro.")
                    continue
                if not self._matches_work_type(location_text):
                    self.status_queue.put(f"Pulando vaga. Modalidade '{location_element.text}' não corresponde ao filtro '{self.work_type}'.")
                    continue
                
                self.status_queue.put(f"Localização OK: '{location_element.text}'.")

                try:
                    job.find_element(*self.EASY_APPLY_TAG)
                    self.status_queue.put("Vaga simplificada encontrada. Pulando no modo de busca normal.")
                    continue
                except NoSuchElementException:
                    try:
                        self.status_queue.put("VAGA NORMAL: Abrindo os detalhes da vaga...")
                        job_url = job.find_element(*self.JOB_TITLE_LINK).get_attribute("href")
                        job_url = self._canonical_job_url(job_url)
                        external_window = None
                        try:
                            job.find_element(*self.JOB_TITLE_LINK).click()
                        except (NoSuchElementException, StaleElementReferenceException):
                            self.driver.execute_script("arguments[0].click();", job)
                        self.status_queue.put("Painel da vaga aberto. Abrindo o link em uma aba dedicada...")

                        self.driver.switch_to.new_window("tab")
                        self.open_url(job_url)
                        external_window = self.driver.current_window_handle
                        self.status_queue.put(f"Link da vaga aberto: {self.driver.current_url}. Procurando o botão 'Candidatar-se'...")

                        external_apply_button = None
                        for locator in (
                            self.EXTERNAL_APPLY_BUTTON,
                            self.EXTERNAL_APPLY_BUTTON_FALLBACK,
                            self.EXTERNAL_APPLY_BUTTON_GENERIC,
                            self.EXTERNAL_APPLY_BUTTON_TEXT,
                        ):
                            external_apply_button = self._find_clickable_element(locator, 10)
                            if external_apply_button is not None:
                                break

                        if external_apply_button is None:
                            raise TimeoutException("Botão 'Candidatar-se' não apareceu na página da vaga.")
                        self._click_external_apply_button(external_apply_button)
                        self.status_queue.put("Botão 'Candidatar-se' clicado. Aguardando a candidatura no site da empresa...")
                        for locator in (self.EXTERNAL_CONTINUE_BUTTON, self.EXTERNAL_CONTINUE_BUTTON_FALLBACK):
                            continue_button = self._find_clickable_element(locator, 5)
                            if continue_button is not None:
                                continue_button.click()
                                self.status_queue.put("Modal de compartilhamento de perfil encontrado. Botão 'Continuar' clicado.")
                                break
                        time.sleep(2)

                        self._wait_for_external_tab_close(external_window, main_window)
                        self._confirm_offsite_application()
                    except Exception as e:
                        self.status_queue.put(f"Não foi possível abrir a candidatura por link: {e}")
                        try:
                            if external_window and external_window in self.driver.window_handles:
                                self.driver.switch_to.window(external_window)
                                self.driver.close()
                            self._restore_main_window(main_window)
                        except Exception as restore_error:
                            self.status_queue.put(f"ERRO: Não foi possível recuperar a aba principal: {restore_error}")
                
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