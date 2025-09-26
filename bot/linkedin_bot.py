# bot/linkedin_bot.py
import json
import os
import time
import threading
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from pages.login_page import LoginPage
from pages.jobs_page import JobsPage
import config

class LinkedinBot:
    """
    Orquestra o fluxo completo de automação do LinkedIn, com gerenciamento de sessão,
    paginação e controle externo por uma interface gráfica (via threads).
    """

    # Locator para um elemento que só existe quando o usuário está logado.
    # Este seletor aponta para o botão/link que abre o menu do perfil ("Eu").
    LOGGED_IN_INDICATOR = (By.CSS_SELECTOR, "button.global-nav__primary-link[aria-expanded]")

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event):
        self.driver = driver
        self.status_queue = status_queue
        # A answer_queue não é usada diretamente aqui, mas precisa ser passada para a JobsPage
        
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.login_page = LoginPage(self.driver, self.status_queue)
        self.jobs_page = JobsPage(self.driver, status_queue, answer_queue, self.pause_event, self.stop_event)
    
    def _save_session(self):
        """Salva os cookies de sessão em um arquivo JSON."""
        with open(config.SESSION_FILE, 'w') as file:
            json.dump(self.driver.get_cookies(), file)
        self.status_queue.put("Sessão salva com sucesso.")

    def _load_session(self) -> bool:
        """Carrega os cookies de sessão de um arquivo JSON, se existir."""
        if not os.path.exists(config.SESSION_FILE):
            return False
        
        with open(config.SESSION_FILE, 'r') as file:
            cookies = json.load(file)
            for cookie in cookies:
                if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                    cookie['sameSite'] = 'None'
                self.driver.add_cookie(cookie)
        return True

    def _is_logged_in(self) -> bool:
        """
        Verifica se a sessão é válida procurando por um elemento específico
        da interface de usuário logada, como o ícone do perfil.
        """
        try:
            # Não força a navegação. Apenas verifica a página atual.
            # Espera no máximo 5 segundos pelo elemento aparecer.
            wait = self.login_page.wait
            wait.until(EC.presence_of_element_located(self.LOGGED_IN_INDICATOR))
            return True
        except TimeoutException:
            # Se o elemento não for encontrado após 5 segundos, não estamos logados.
            return False

    def run(self):
        """
        Executa o fluxo completo do bot, incluindo login/sessão, busca e o loop de paginação
        que se recupera de recarregamentos de página.
        """
        try:
            self.status_queue.put("Iniciando o Copiloto LinkedIn...")
            
            # --- Etapa 1: Verificação de Login Aprimorada ---
            self.status_queue.put("Verificando status do login na página atual...")
            if "linkedin.com" not in self.driver.current_url:
                self.driver.get("https://www.linkedin.com/feed/")
                time.sleep(2)

            if self._is_logged_in():
                self.status_queue.put("Sessão válida detectada. Login pulado.")
            else:
                self.status_queue.put("Nenhuma sessão válida detectada. Tentando realizar novo login...")
                self.driver.get(config.URL_LOGIN)
                self.login_page.login(config.LINKEDIN_EMAIL, config.LINKEDIN_SENHA)
                time.sleep(5) 
                if not self._is_logged_in():
                    self.status_queue.put("ERRO: O login falhou. Verifique suas credenciais no .env e a página do LinkedIn.")
                    return
                self._save_session()

            # --- Etapa 2: Busca Inicial de Vagas ---
            self.jobs_page.search_jobs(config.PALAVRAS_CHAVE, config.LOCALIZACAO, config.URL_BASE_VAGAS)
            
            # --- Etapa 3: Loop de Paginação com Recuperação de Recarregamento ---
            page_number = 1
            while True:
                self.jobs_page._check_control_signals()
                self.status_queue.put(f"================== PROCESSANDO PÁGINA {page_number} ==================")
                
                application_made = self.jobs_page.apply_to_jobs_on_page(config.CAMINHO_CURRICULO)
                
                if application_made:
                    self.status_queue.put("Candidatura realizada. Re-analisando a página atual devido ao recarregamento...")
                    time.sleep(5) # Dê um tempo extra para a página recarregar completamente
                    continue

                can_go_next = self.jobs_page.go_to_next_page()
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