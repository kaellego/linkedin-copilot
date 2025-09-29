# browser/driver_factory.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def create_driver() -> webdriver.Chrome:
    """
    Cria uma inst?ncia do Chrome WebDriver conectando-se a um navegador j? existente
    com op??es aprimoradas e compat?veis para evitar detec??o.
    """
    chrome_options = Options()
    
    # Conecta ao navegador em modo de depura??o
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    # Argumentos para mascarar a automa??o
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # REMOVIDO: Esta linha tamb?m pode causar erros em algumas vers?es e foi removida
    # para garantir a m?xima compatibilidade.
    # chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)

    # Adicional: Muda uma propriedade do navegador para dificultar a detec??o
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
          """
        },
    )
    
    return driver