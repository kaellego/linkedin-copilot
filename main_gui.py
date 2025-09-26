# main_gui.py
import PySimpleGUI as sg
import threading
import queue
import time
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot

def bot_thread_worker(status_queue: queue.Queue, pause_event: threading.Event, stop_event: threading.Event):
    """Função que será executada na thread secundária."""
    driver = None
    try:
        driver = create_driver()
        bot = LinkedinBot(driver, status_queue, pause_event, stop_event)
        bot.run()
    except InterruptedError as e:
        status_queue.put(f"Processo finalizado pelo usuário: {e}")
    except Exception as e:
        status_queue.put(f"Um erro crítico ocorreu na thread do bot: {e}")
    finally:
        if driver:
            driver.quit()
        status_queue.put("--- THREAD DO BOT ENCERRADA ---")

def main():
    sg.theme('Reddit')

    # Layout da interface
    layout = [
        [sg.Text('Copiloto LinkedIn', font=('Helvetica', 16))],
        [sg.Multiline(size=(80, 20), key='-LOG-', autoscroll=True, reroute_stdout=False, write_only=True)],
        [
            sg.Button('Iniciar', key='-START-', size=(10, 1)),
            sg.Button('Pausar', key='-PAUSE-', disabled=True, size=(10, 1)),
            sg.Button('Continuar', key='-RESUME-', disabled=True, size=(10, 1)),
            sg.Button('Parar', key='-STOP-', disabled=True, size=(10, 1))
        ]
    ]

    window = sg.Window('Painel de Controle do Robô', layout, keep_on_top=True, finalize=True)

    status_queue = queue.Queue()
    pause_event = threading.Event()
    stop_event = threading.Event()
    bot_thread = None

    while True:
        event, values = window.read(timeout=100) # Timeout para a GUI não bloquear

        # Atualiza o log com mensagens da fila
        try:
            message = status_queue.get_nowait()
            window['-LOG-'].print(f'[{time.strftime("%H:%M:%S")}] {message}')
            if "--- THREAD DO BOT ENCERRADA ---" in message:
                # Reativa o botão Iniciar quando o bot termina
                window['-START-'].update(disabled=False)
                window['-PAUSE-'].update(disabled=True)
                window['-RESUME-'].update(disabled=True)
                window['-STOP-'].update(disabled=True)
        except queue.Empty:
            pass

        if event == sg.WIN_CLOSED:
            if bot_thread and bot_thread.is_alive():
                stop_event.set() # Sinaliza para a thread parar
                bot_thread.join() # Espera a thread terminar
            break

        elif event == '-START-':
            window['-START-'].update(disabled=True)
            window['-PAUSE-'].update(disabled=False)
            window['-STOP-'].update(disabled=False)
            
            pause_event.set() # Garante que o bot comece rodando (não pausado)
            stop_event.clear() # Limpa o sinal de parada

            bot_thread = threading.Thread(
                target=bot_thread_worker,
                args=(status_queue, pause_event, stop_event),
                daemon=True
            )
            bot_thread.start()

        elif event == '-PAUSE-':
            pause_event.clear() # Sinaliza para a thread pausar
            window['-PAUSE-'].update(disabled=True)
            window['-RESUME-'].update(disabled=False)

        elif event == '-RESUME-':
            pause_event.set() # Sinaliza para a thread continuar
            window['-RESUME-'].update(disabled=True)
            window['-PAUSE-'].update(disabled=False)
        
        elif event == '-STOP-':
            stop_event.set() # Sinaliza para a thread parar
            window['-STOP-'].update(disabled=True)

    window.close()

if __name__ == '__main__':
    main()