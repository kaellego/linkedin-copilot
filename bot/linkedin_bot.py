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
    Orquestra o fluxo completo de automação do LinkedIn, com gerenciamento de sessão,
    paginação e controle externo por uma interface gráfica (via threads),
    operando em um modo de candidatura definido pelo usuário na inicialização.
    """
    
    # Locator para um elemento que só existe quando o usuário está logado.
    # Este seletor aponta para o botão/link que abre o menu do perfil ("Eu").
    LOGGED_IN_INDICATOR = (By.CSS_SELECTOR, "button.global-nav__primary-link[aria-expanded]")

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event, is_normal_apply_mode: bool):
        self.driver = driver
        self.status_queue = status_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        
        # O modo de operação agora é definido na inicialização
        self.is_normal_apply_mode = is_normal_apply_mode
        self.easy_apply_limit_reached = False # Estado interno para controle de limite

        # Instancia as páginas, passando os objetos de controle necessários
        self.login_page = LoginPage(self.driver, self.status_queue)
        self.job_search_page = JobSearchPage(self.driver, status_queue, answer_queue, self.pause_event, self.stop_event)

    def _is_logged_in(self) -> bool:
        """
        Verifica se a sessão é válida procurando por um elemento específico
        da interface de usuário logada.
        """
        try:
            # Usa um tempo de espera curto para uma verificação rápida
            wait = self.login_page.wait
            wait.until(EC.presence_of_element_located(self.LOGGED_IN_INDICATOR))
            return True
        except TimeoutException:
            return False

    def run(self):
        """
        Executa o fluxo completo do bot, incluindo login/sessão, busca e o loop de paginação.
        """
        try:
            self.status_queue.put("Iniciando o Copiloto LinkedIn...")
            
            # --- Etapa 1: Verificação de Login ---
            self.status_queue.put("Verificando status do login na página atual...")
            if "linkedin.com" not in self.driver.current_url:
                self.driver.get("https://www.linkedin.com/feed/")
                time.sleep(2)

            if not self._is_logged_in():
                self.status_queue.put("ERRO: O navegador não está logado no LinkedIn. Por favor, faça o login manualmente e reinicie o robô.")
                return

            self.status_queue.put("Sessão válida detectada. Login pulado.")
            
            # --- Etapa 2: Busca Inicial de Vagas de acordo com o modo selecionado ---
            self.job_search_page.search_jobs(
                config.PALAVRAS_CHAVE,
                config.LOCALIZACAO,
                config.URL_BASE_VAGAS,
                easy_apply_mode=not self.is_normal_apply_mode
            )
            
            # --- Etapa 3: Loop de Paginação e Candidatura ---
            page_number = 1
            while True:
                self.job_search_page._check_control_signals()
                self.status_queue.put(f"================== PROCESSANDO PÁGINA {page_number} ==================")
                
                # Processa as vagas na página, passando o modo de operação
                status = self.job_search_page.apply_to_jobs_on_page(config.CAMINHO_CURRICULO, self.is_normal_apply_mode)
                
                if status == "LIMIT_REACHED":
                    self.status_queue.put("!!! LIMITE DE CANDIDATURAS SIMPLIFICADAS ATINGIDO !!!")
                    self.is_normal_apply_mode = True # Força a mudança para o modo normal
                    self.status_queue.put("Trocando para o modo de busca de vagas normais e reiniciando a busca...")
                    self.job_search_page.search_jobs(config.PALAVRAS_CHAVE, config.LOCALIZACAO, config.URL_BASE_VAGAS, easy_apply_mode=False)
                    page_number = 1
                    continue

                if status == "PAGE_RELOADED":
                    self.status_queue.put("Candidatura realizada. Re-analisando a página atual devido ao recarregamento...")
                    continue

                # Se a página foi processada normalmente, tenta ir para a próxima.
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
                self.status_queue.put(f"Screenshot salvo: debug_screenshots/fatal_error_{timestamp}.png")
            except Exception as screenshot_error:
                self.status_queue.put(f"Falha ao salvar screenshot: {screenshot_error}")