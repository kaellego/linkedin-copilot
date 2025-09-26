# pages/login_page.py
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from pages.base_page import BasePage
from selenium.common.exceptions import TimeoutException
import time
import random

import threading
from queue import Queue
from selenium.webdriver.remote.webdriver import WebDriver

class LoginPage(BasePage):
    """Representa a página de login do LinkedIn, agora adaptativa."""
    
    # --- Locators ---
    # Locators do login padrão
    USERNAME_INPUT = (By.ID, "username")
    PASSWORD_INPUT = (By.ID, "password")
    LOGIN_BUTTON = (By.XPATH, "//button[@type='submit']")

    # NOVO: Locator para o botão de "login com um clique" (ex: "Entrar como Wellington S.")
    # Usamos um seletor CSS que procura um botão cujo 'aria-label' COMEÇA COM "Entrar como"
    ONE_CLICK_SIGN_IN_BUTTON = (By.CSS_SELECTOR, "button[aria-label^='Entrar como']")

    def __init__(self, driver: WebDriver, status_queue: Queue):
        super().__init__(driver)
        self.status_queue = status_queue

    def login(self, email: str, senha: str):
        """
        Executa uma sequência de login adaptativa.
        Primeiro tenta o login de um clique, se falhar, tenta o login padrão.
        """
        print("Executando sequência de login adaptativa...")
        try:
            # --- TENTATIVA 1: Login com um clique ---
            self.status_queue.put("Procurando por botão de login rápido...")
            
            # Espera até 10 segundos pelo botão de login rápido
            one_click_button = self.wait.until(EC.element_to_be_clickable(self.ONE_CLICK_SIGN_IN_BUTTON))
            self.status_queue.put("Botão de login rápido encontrado. Clicando...")
            one_click_button.click()
            
            # Após clicar, a página geralmente pede apenas a senha.
            time.sleep(random.uniform(2, 4))
            self.status_queue.put("Inserindo a senha...")
            self._send_keys(self.PASSWORD_INPUT, senha)
            time.sleep(random.uniform(1, 2))
            
            # Encontra o campo de senha novamente para enviar a tecla Enter
            password_field = self._find_element(self.PASSWORD_INPUT)
            password_field.send_keys(Keys.RETURN)
            
            self.status_queue.put("Login com um clique realizado com sucesso.")

        except TimeoutException:
            # --- TENTATIVA 2: Login Padrão (Fallback) ---
            self.status_queue.put("Login rápido não disponível. Usando método padrão...")
            
            # Se o botão de um clique não for encontrado, executa a lógica original.
            self._send_keys(self.USERNAME_INPUT, email)
            time.sleep(random.uniform(0.5, 1.5))
            self._send_keys(self.PASSWORD_INPUT, senha)
            time.sleep(random.uniform(0.5, 1.5))
            self._click(self.LOGIN_BUTTON)
            
            self.status_queue.put("Login padrão realizado com sucesso.")
        except Exception as e:
            self.status_queue.put(f"Ocorreu um erro inesperado durante o login: {e}")
            raise # Re-lança a exceção para que seja capturada pela thread principal