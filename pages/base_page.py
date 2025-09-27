# pages/base_page.py
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from typing import Tuple
import time

class BasePage:
    """
    Classe base para todas as outras páginas, agora com funcionalidades
    de depuração visual (destaque de elementos).
    """
    
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)

    def _highlight_element(self, element: WebElement, color: str = 'red'):
        """Aplica um destaque visual a um elemento usando JavaScript."""
        original_style = element.get_attribute('style')
        style_string = f"border: 3px dashed {color};"
        self.driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", element, style_string)
        # Retorna o estilo original para que possamos restaurá-lo depois
        return original_style

    def _unhighlight_element(self, element: WebElement, original_style: str):
        """Remove o destaque de um elemento, restaurando seu estilo original."""
        self.driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", element, original_style)

    def _find_element(self, locator: Tuple[str, str]) -> WebElement:
        """Encontra e retorna um elemento esperando ele estar visível."""
        try:
            return self.wait.until(EC.visibility_of_element_located(locator))
        except TimeoutException:
            raise TimeoutException(f"Elemento com localizador {locator} não encontrado na página {self.driver.current_url}")

    def _click(self, locator: Tuple[str, str]):
        """Espera um elemento ser clicável, o destaca, e então clica nele."""
        element = self.wait.until(EC.element_to_be_clickable(locator))
        original_style = self._highlight_element(element)
        time.sleep(0.3) # Pequena pausa para o olho humano ver o destaque
        element.click()
        self._unhighlight_element(element, original_style)

    def _send_keys(self, locator: Tuple[str, str], text: str):
        """Encontra um elemento, o destaca, e insere texto nele."""
        element = self._find_element(locator)
        original_style = self._highlight_element(element)
        time.sleep(0.3)
        element.clear()
        element.send_keys(text)
        self._unhighlight_element(element, original_style)

    def open_url(self, url: str):
        """Navega para uma URL específica."""
        self.driver.get(url)