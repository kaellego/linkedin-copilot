# pages/base_page.py
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from typing import Tuple
import config
from utils.privacy import sanitize_url

class BasePage:
    """
    Classe base para todas as outras páginas, com funcionalidades
    de interação e depuração visual (destaque de elementos).
    """
    
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, config.DEFAULT_WAIT_SECONDS, poll_frequency=0.2)

    def _highlight_element(self, element: WebElement, color: str = 'red'):
        """Aplica um destaque visual a um elemento usando JavaScript."""
        try:
            original_style = element.get_attribute('style')
            style_string = f"border: 3px dashed {color};"
            self.driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", element, style_string)
            return original_style
        except:
            # Se o elemento se tornar 'stale' durante o highlight, ignora.
            return ""

    def _unhighlight_element(self, element: WebElement, original_style: str):
        """Remove o destaque de um elemento, restaurando seu estilo original."""
        try:
            self.driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", element, original_style)
        except:
            # Se o elemento se tornar 'stale', não há o que limpar.
            pass

    def _find_element(self, locator: Tuple[str, str], timeout: float = None) -> WebElement:
        """Encontra e retorna um elemento esperando ele estar visível."""
        try:
            waiter = self.wait if timeout is None else WebDriverWait(self.driver, timeout, poll_frequency=0.2)
            return waiter.until(EC.visibility_of_element_located(locator))
        except TimeoutException:
            raise TimeoutException(f"Elemento com localizador {locator} não encontrado na página {sanitize_url(self.driver.current_url)}")

    def _click(self, locator: Tuple[str, str]):
        """Espera um elemento ser clicável, o destaca, e então clica nele."""
        element = self.wait.until(EC.element_to_be_clickable(locator))
        original_style = self._highlight_element(element)
        try:
            element.click()
        finally:
            self._unhighlight_element(element, original_style)

    def _send_keys(self, locator: Tuple[str, str], text: str):
        """Encontra um elemento, o destaca, e insere texto nele."""
        element = self._find_element(locator)
        original_style = self._highlight_element(element)
        try:
            element.clear()
            element.send_keys(text)
        finally:
            self._unhighlight_element(element, original_style)

    def open_url(self, url: str):
        """Navega para uma URL específica, recuperando falhas transitórias."""
        last_error = None
        for attempt in range(3):
            try:
                self.driver.get(url)
                return
            except WebDriverException as error:
                last_error = error
                if "ERR_CONNECTION_CLOSED" not in str(error) or attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        raise last_error
