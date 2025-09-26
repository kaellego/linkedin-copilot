# utils/controls.py
import os
import time
import config

# Define uma exceção customizada para o sinal de parada
class StopSignalException(Exception):
    pass

def check_for_pause_or_stop():
    """
    Verifica a existência de arquivos de sinalização para pausar ou parar a execução.
    """
    # Verifica primeiro o sinal de parada
    if os.path.exists(config.STOP_FLAG_FILE):
        print("Sinal de parada detectado. Encerrando o bot de forma segura...")
        # Lança uma exceção que será capturada no main.py para encerrar
        raise StopSignalException("Stop flag detected")

    # Verifica o sinal de pausa
    if os.path.exists(config.PAUSE_FLAG_FILE):
        print("\n--- ROBO PAUSADO ---")
        print("Para continuar, delete o arquivo 'pause.flag' na pasta do projeto.")
        print("Para parar completamente, crie o arquivo 'stop.flag'.")
        
        while os.path.exists(config.PAUSE_FLAG_FILE):
            # Re-verifica o sinal de parada mesmo enquanto pausado
            if os.path.exists(config.STOP_FLAG_FILE):
                print("Sinal de parada detectado durante a pausa...")
                raise StopSignalException("Stop flag detected during pause")
            
            time.sleep(2) # Espera 2 segundos antes de verificar novamente para não sobrecarregar o CPU
            
        print("--- ROBO CONTINUANDO ---")