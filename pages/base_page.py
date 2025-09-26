# pages/base_page.py
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from typing import Tuple

class BasePage:
    """Classe base que todas as outras páginas herdarão."""
    
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)

    def _find_element(self, locator: Tuple[str, str]) -> WebElement:
        """Encontra e retorna um elemento esperando ele estar visível."""
        try:
            return self.wait.until(EC.visibility_of_element_located(locator))
        except TimeoutException:
            raise TimeoutException(f"Elemento com localizador {locator} não encontrado na página {self.driver.current_url}")

    def _click(self, locator: Tuple[str, str]):
        """Espera um elemento ser clicável e então clica nele."""
        element = self.wait.until(EC.element_to_be_clickable(locator))
        element.click()

    def _send_keys(self, locator: Tuple[str, str], text: str):
        """Encontra um elemento e insere texto nele."""
        element = self._find_element(locator)
        element.clear()
        element.send_keys(text)

    def open_url(self, url: str):
        """Navega para uma URL específica."""
        self.driver.get(url)