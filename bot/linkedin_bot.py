# bot/linkedin_bot.py
import time
import threading
import json
import os
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from pages.login_page import LoginPage
from pages.job_search_page import JobSearchPage
import config

class LinkedinBot:
    """
    Orquestrador principal do robô. Gerencia o estado (modo de operação) e
    chama os métodos corretos da JobSearchPage (process_easy_apply_jobs ou process_normal_jobs).
    """
    LOGGED_IN_INDICATOR = (By.CSS_SELECTOR, "div[data-testid='primary-nav']")

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event, is_normal_apply_mode: bool):
        self.driver = driver
        self.status_queue = status_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.is_normal_apply_mode = is_normal_apply_mode

        self.login_page = LoginPage(self.driver, self.status_queue)
        self.job_search_page = JobSearchPage(self.driver, status_queue, answer_queue, self.pause_event, self.stop_event)

    def _is_logged_in(self) -> bool:
        try:
            wait = self.login_page.wait
            wait.until(EC.presence_of_element_located(self.LOGGED_IN_INDICATOR))
            return True
        except TimeoutException:
            return False

    def run(self):
        try:
            self.status_queue.put("Iniciando o Copiloto LinkedIn...")
            
            self.status_queue.put("Verificando status do login na página atual...")
            if "linkedin.com" not in self.driver.current_url:
                self.driver.get("https://www.linkedin.com/feed/")
                time.sleep(2)

            if not self._is_logged_in():
                self.status_queue.put("ERRO: O navegador não está logado no LinkedIn. Por favor, faça o login manualmente e reinicie o robô.")
                return

            self.status_queue.put("Sessão válida detectada. Login pulado.")
            
            self.job_search_page.search_jobs(
                config.PALAVRAS_CHAVE,
                config.LOCALIZACAO,
                config.URL_BASE_VAGAS,
                easy_apply_mode=not self.is_normal_apply_mode
            )
            
            page_number = 1
            while True:
                self.job_search_page._check_control_signals()
                self.status_queue.put(f"================== PROCESSANDO PÁGINA {page_number} ==================")
                
                # --- LÓGICA DE DECISÃO CORRIGIDA ---
                if not self.is_normal_apply_mode:
                    # MODO DE CANDIDATURA SIMPLIFICADA
                    status = self.job_search_page.process_easy_apply_jobs(config.CAMINHO_CURRICULO)
                    
                    if status == "LIMIT_REACHED":
                        self.status_queue.put("!!! LIMITE DE CANDIDATURAS ATINGIDO !!!")
                        self.is_normal_apply_mode = True
                        self.status_queue.put("Trocando para o modo de busca de vagas normais e reiniciando a busca...")
                        self.job_search_page.search_jobs(config.PALAVRAS_CHAVE, config.LOCALIZACAO, config.URL_BASE_VAGAS, easy_apply_mode=False)
                        page_number = 1
                        continue

                    if status == "PAGE_RELOADED":
                        self.status_queue.put("Candidatura realizada. Re-analisando a página...")
                        continue
                else:
                    # MODO DE VAGAS NORMAIS
                    self.job_search_page.process_normal_jobs()

                can_go_next = self.job_search_page.go_to_next_page()
                if can_go_next:
                    page_number += 1
                else:
                    break
            
            self.status_queue.put("--- FIM DO PROCESSO ---")

        except InterruptedError as e:
            self.status_queue.put(f"Processo finalizado pelo usuário: {e}")
        except Exception as e:
            self.status_queue.put(f"ERRO FATAL: {e}")
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            try:
                self.driver.save_screenshot(f'debug_screenshots/fatal_error_{timestamp}.png')
                self.status_queue.put(f"Screenshot salvo: {timestamp}.png")
            except Exception as screenshot_error:
                self.status_queue.put(f"Falha ao salvar screenshot: {screenshot_error}")