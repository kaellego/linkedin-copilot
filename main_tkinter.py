# main_tkinter.py
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import threading
import queue
import time
import socket
import subprocess
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot
from services.ai_service import AIService
import config # Importa o config

def bot_thread_worker(status_queue, answer_queue, pause_event, stop_event, is_normal_apply_mode):
    """Função alvo da thread do robô."""
    driver = None
    try:
        driver = create_driver()
        bot = LinkedinBot(driver, status_queue, answer_queue, pause_event, stop_event, is_normal_apply_mode)
        bot.run()
    except Exception as e:
        status_queue.put(f"Um erro crítico ocorreu na thread do bot: {e}")
    finally:
        if driver:
            # Não fecha o driver para que o usuário possa continuar usando o navegador
            # driver.quit() 
            status_queue.put("O robô terminou. Você pode fechar o navegador manualmente.")
        status_queue.put("--- THREAD DO BOT ENCERRADA ---")

class ControlPanelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Painel de Controle do Robô")
        self.geometry("600x450")
        self.attributes('-topmost', True)

        self.bot_thread = None
        self.status_queue = queue.Queue()
        self.answer_queue = queue.Queue()
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.normal_apply_var = tk.BooleanVar()

        self._create_widgets()
        self.check_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _create_widgets(self):
        control_frame = tk.Frame(self)
        control_frame.pack(pady=5, padx=10, fill=tk.X)
        self.mode_checkbox = tk.Checkbutton(control_frame, text="Buscar apenas vagas normais (ignorar 'Candidatura Simplificada')", var=self.normal_apply_var)
        self.mode_checkbox.pack(side=tk.TOP, anchor='w', pady=(0, 10))
        button_frame = tk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        self.start_button = tk.Button(button_frame, text="Iniciar", command=self.start_bot)
        self.pause_button = tk.Button(button_frame, text="Pausar", command=self.pause_bot, state=tk.DISABLED)
        self.resume_button = tk.Button(button_frame, text="Continuar", command=self.resume_bot, state=tk.DISABLED)
        self.stop_button = tk.Button(button_frame, text="Parar", command=self.stop_bot, state=tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.pause_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.resume_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.log_text = scrolledtext.ScrolledText(self, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)

    def check_and_start_chrome_debug(self) -> bool:
        """Verifica se a porta de depuração está ativa; se não, inicia o Chrome."""
        self.update_log("Verificando porta de depuração do Chrome (9222)...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 9222))
        sock.close()

        if result == 0:
            self.update_log("Porta 9222 já está em uso. Assumindo que o Chrome já está rodando.")
            return True
        else:
            self.update_log("Porta 9222 livre. Iniciando Chrome em modo de depuração...")
            command = f'"{config.CHROME_EXECUTABLE_PATH}" --remote-debugging-port=9222 --user-data-dir="{config.CHROME_DEBUG_PROFILE_PATH}"'
            try:
                subprocess.Popen(command, shell=True)
                self.update_log("Comando para iniciar o Chrome executado. Aguardando 7 segundos...")
                time.sleep(7) # Dá tempo para o navegador iniciar
                return True
            except FileNotFoundError:
                error_msg = f"ERRO: Não foi possível encontrar 'chrome.exe'. Verifique o caminho em config.py:\n{config.CHROME_EXECUTABLE_PATH}"
                self.update_log(error_msg)
                messagebox.showerror("Erro de Configuração", error_msg)
                return False
            except Exception as e:
                self.update_log(f"ERRO ao iniciar o Chrome: {e}")
                messagebox.showerror("Erro Inesperado", f"Ocorreu um erro ao tentar iniciar o Chrome:\n{e}")
                return False

    def start_bot(self):
        # Desabilita botões imediatamente para evitar cliques duplos
        self.start_button.config(state=tk.DISABLED)
        self.mode_checkbox.config(state=tk.DISABLED)
        
        # Roda a verificação e inicialização do Chrome
        if not self.check_and_start_chrome_debug():
            self.reset_ui() # Reativa a UI se o Chrome não pôde ser iniciado
            return

        # Se o Chrome iniciou com sucesso, configura e inicia a thread do robô
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        
        self.pause_event.set()
        self.stop_event.clear()

        is_normal_mode = self.normal_apply_var.get()

        self.bot_thread = threading.Thread(
            target=bot_thread_worker,
            args=(self.status_queue, self.answer_queue, self.pause_event, self.stop_event, is_normal_mode),
            daemon=True
        )
        self.bot_thread.start()

    # ... (O resto dos métodos permanecem os mesmos da versão anterior) ...
    def update_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def check_queue(self):
        try:
            message = self.status_queue.get_nowait()
            if message.startswith("USER_INPUT_REQUIRED|"):
                question = message.split("|", 1)[1]
                self.update_log(f"AÇÃO NECESSÁRIA: O robô precisa da sua resposta para a pergunta: '{question}'")
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.DISABLED)
                answer = simpledialog.askstring("Pergunta do Recrutador", f"A automação encontrou uma pergunta que não sabe responder:\n\n'{question}'\n\nForneça sua resposta abaixo:")
                self.answer_queue.put(answer)
                if answer:
                    self.update_log(f"Sua resposta '{answer}' foi enviada ao robô.")
                else:
                    self.update_log("Você cancelou a pergunta. O robô irá pular a candidatura.")
                if not self.stop_event.is_set():
                    self.pause_button.config(state=tk.NORMAL)
            else:
                self.update_log(message)
                if "--- THREAD DO BOT ENCERRADA ---" in message:
                    self.reset_ui()
        except queue.Empty:
            pass
        finally:
            self.after(200, self.check_queue)

    def pause_bot(self):
        self.pause_event.clear()
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.NORMAL)

    def resume_bot(self):
        self.pause_event.set()
        self.resume_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)

    def stop_bot(self):
        self.stop_event.set()
        self.pause_event.set()
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        
    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.mode_checkbox.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

    def on_closing(self):
        if self.bot_thread and self.bot_thread.is_alive():
            if messagebox.askyesno("Sair", "O robô está em execução. Deseja pará-lo e sair?"):
                self.stop_event.set()
                self.pause_event.set()
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":
    app = ControlPanelApp()
    app.mainloop()