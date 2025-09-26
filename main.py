# main.py
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot
from utils.controls import StopSignalException # NOVO IMPORT
import config # NOVO IMPORT
import time
import os

def cleanup_flags():
    """Remove os arquivos de flag no início e no fim da execução."""
    if os.path.exists(config.PAUSE_FLAG_FILE):
        os.remove(config.PAUSE_FLAG_FILE)
    if os.path.exists(config.STOP_FLAG_FILE):
        os.remove(config.STOP_FLAG_FILE)

if __name__ == "__main__":
    cleanup_flags() # Limpa flags de uma execução anterior
    
    if not os.path.exists('debug_screenshots'):
        os.makedirs('debug_screenshots')
        
    driver = None
    try:
        driver = create_driver()
        bot = LinkedinBot(driver)
        bot.run()
        
    # NOVO: Captura a exceção de parada para encerrar de forma limpa
    except StopSignalException as e:
        print(f"\nProcesso interrompido pelo usuário: {e}")
        
    except Exception as e:
        print(f"Ocorreu um erro fatal na execução do bot: {e}")
        if driver:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            driver.save_screenshot(f'debug_screenshots/fatal_error_{timestamp}.png')
            print(f"Screenshot do erro salvo em: debug_screenshots/fatal_error_{timestamp}.png")

    finally:
        cleanup_flags() # Garante que os flags sejam removidos ao final
        if driver:
            print("Fechando o navegador...")
            # time.sleep(15) # Opcional, pode remover para fechar mais rápido
            driver.quit()