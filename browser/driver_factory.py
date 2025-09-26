# browser/driver_factory.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

def create_driver() -> webdriver.Chrome:
    """
    Cria uma instancia do Chrome WebDriver conectando-se a um navegador ja existente.
    """
    chrome_options = Options()
    
    # A MÁGICA ACONTECE AQUI:
    # Esta opção diz ao Selenium para se conectar ao Chrome na porta 9222
    # em vez de iniciar um novo.
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    # Não precisamos mais do webdriver-manager ou do Service, pois não estamos iniciando um novo driver.
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def create_driver_old() -> webdriver.Chrome:
    """Cria e retorna uma instancia configurada do Chrome WebDriver."""
    chrome_options = Options()
    # Tenta se passar por um navegador comum
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Ignora erros de certificado SSL (ajuda com os erros de handshake)
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging']) # Limpa o log do DevTools
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver