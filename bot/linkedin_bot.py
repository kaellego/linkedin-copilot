# bot/linkedin_bot.py
import time
import threading
import json
import os
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from pages.login_page import LoginPage
from pages.job_search_page import JobSearchPage
import config
from utils.privacy import sanitize_url, sanitize_text
from utils.debug_artifacts import save_failure_context
from utils.privacy import sanitize_text

class LinkedinBot:
    """
    Orquestrador principal do robô. Gerencia o estado (modo de operação) e
    chama os métodos corretos da JobSearchPage (process_easy_apply_jobs ou process_normal_jobs).
    """
    LOGGED_IN_INDICATORS = (
        (By.CSS_SELECTOR, "div[role='search']"),
        (By.CSS_SELECTOR, "input[placeholder*='Pesquisar']"),
        (By.CSS_SELECTOR, "a[href*='/feed/']"),
        (By.CSS_SELECTOR, "nav[aria-label]"),
    )

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event, application_mode: str):
        self.driver = driver
        self.status_queue = status_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.application_mode = application_mode

        self.login_page = LoginPage(self.driver, self.status_queue)
        self.job_search_page = JobSearchPage(self.driver, status_queue, answer_queue, self.pause_event, self.stop_event)

    def _is_logged_in(self) -> bool:
        try:
            wait = self.login_page.wait
            wait.until(EC.any_of(*(
                EC.presence_of_element_located(locator)
                for locator in self.LOGGED_IN_INDICATORS
            )))
            return True
        except TimeoutException:
            return False

    def _open_url_with_retry(self, url: str):
        last_error = None
        for attempt in range(3):
            try:
                self.driver.get(url)
                return
            except WebDriverException as error:
                last_error = error
                if "ERR_CONNECTION_CLOSED" not in str(error) or attempt == 2:
                    raise
                self.status_queue.put(
                    f"AVISO: conexão encerrada ao abrir a página. Tentativa {attempt + 2}/3..."
                )
                time.sleep(2 * (attempt + 1))
        raise last_error

    def run(self):
        try:
            config.validate_runtime_config()
            config.ensure_runtime_dirs()
            self.status_queue.put("Iniciando o Copiloto LinkedIn...")
            
            self.status_queue.put("Verificando status do login na página atual...")
            if "linkedin.com" not in self.driver.current_url:
                self._open_url_with_retry("https://www.linkedin.com/feed/")

            if not self._is_logged_in():
                self.status_queue.put(
                    "ERRO: O navegador conectado na porta 9222 não está logado no LinkedIn. "
                    f"URL atual: {sanitize_url(self.driver.current_url)}. "
                    "Faça login nesse mesmo perfil do Chrome e reinicie o robô."
                )
                return

            self.status_queue.put("Sessão válida detectada. Login pulado.")
            current_mode = "easy" if self.application_mode in ("easy", "all") else "link"
            self.job_search_page.search_jobs(
                config.PALAVRAS_CHAVE,
                config.LOCALIZACAO,
                config.URL_BASE_VAGAS,
                easy_apply_mode=self.application_mode == "easy",
                work_type=config.TIPO_VAGA,
            )
            
            page_number = 1
            while True:
                self.job_search_page._check_control_signals()
                self.status_queue.put(f"================== PROCESSANDO PÁGINA {page_number} ==================")
                
                # --- LÓGICA DE DECISÃO CORRIGIDA ---
                if current_mode == "easy":
                    # MODO DE CANDIDATURA SIMPLIFICADA
                    status = self.job_search_page.process_easy_apply_jobs(
                        config.CAMINHO_CURRICULO,
                        process_normal_jobs=self.application_mode == "all",
                    )
                    
                    if status == "LIMIT_REACHED":
                        self.status_queue.put("!!! LIMITE DE CANDIDATURAS ATINGIDO !!!")
                        if self.application_mode == "all":
                            self.status_queue.put("Limite de simplificadas atingido. Processando vagas normais por link nesta página...")
                            self.job_search_page.process_normal_jobs()
                            current_mode = "link"
                            continue
                        self.status_queue.put("Encerrando: o modo selecionado aceita apenas candidatura simplificada.")
                        break

                    if status == "PAGE_RELOADED":
                        self.status_queue.put("Candidatura realizada. Re-analisando a página...")
                        if self.application_mode != "all":
                            continue

                    normal_jobs_processed = status == "NORMAL_PROCESSED"

                    if self.application_mode == "all" and not normal_jobs_processed:
                        self.status_queue.put("Processando vagas normais por link nesta página...")
                        self.job_search_page.process_normal_jobs()
                else:
                    # MODO DE VAGAS NORMAIS
                    self.job_search_page.process_normal_jobs()

                can_go_next = self.job_search_page.go_to_next_page()
                if can_go_next:
                    page_number += 1
                else:
                    if self.application_mode == "all":
                        self.status_queue.put("Todas as vagas da busca foram processadas.")
                        break
                    break

            self.status_queue.put("--- FIM DO PROCESSO ---")

        except InterruptedError as e:
            self.status_queue.put(f"Processo finalizado pelo usuário: {sanitize_text(e)}")
        except Exception as e:
            self.status_queue.put(f"ERRO FATAL: {sanitize_text(e)}")
            try:
                folder = save_failure_context(self.driver, "bot_fatal", e)
                self.status_queue.put(f"Contexto HTML sanitizado salvo em: {folder}")
            except Exception:
                self.status_queue.put("Falha ao salvar contexto da execução.")
