# main.py
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot
from utils.controls import StopSignalException # NOVO IMPORT
import config # NOVO IMPORT
import os
from utils.debug_artifacts import save_failure_context
from utils.privacy import sanitize_text

def cleanup_flags():
    """Remove os arquivos de flag no início e no fim da execução."""
    if os.path.exists(config.PAUSE_FLAG_FILE):
        os.remove(config.PAUSE_FLAG_FILE)
    if os.path.exists(config.STOP_FLAG_FILE):
        os.remove(config.STOP_FLAG_FILE)

if __name__ == "__main__":
    cleanup_flags() # Limpa flags de uma execução anterior
    
    driver = None
    try:
        config.ensure_runtime_dirs()
        driver = create_driver()
        bot = LinkedinBot(driver)
        bot.run()
        
    # NOVO: Captura a exceção de parada para encerrar de forma limpa
    except StopSignalException as e:
        print(f"\nProcesso interrompido pelo usuário: {e}")
        
    except Exception as e:
        print(f"Ocorreu um erro fatal na execução do bot: {sanitize_text(e)}")
        if driver:
            try:
                folder = save_failure_context(driver, "main_fatal", e)
                print(f"Contexto HTML sanitizado salvo em: {folder}")
            except Exception:
                print("Falha ao salvar contexto da execução.")

    finally:
        cleanup_flags() # Garante que os flags sejam removidos ao final
        if driver:
            print("Fechando o navegador...")
            # time.sleep(15) # Opcional, pode remover para fechar mais rápido
            driver.quit()
