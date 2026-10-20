# main_tkinter.py
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk
import threading
import queue
import time
import socket
import subprocess
import logging
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot
from services.ai_service import AIService
import config

# --- Configuração do Logging ---
logging.basicConfig(
    filename='bot_execution.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def bot_thread_worker(status_queue, answer_queue, pause_event, stop_event, application_mode, keywords, location, work_type):
    """Função alvo da thread do robô."""
    driver = None
    try:
        # Atualiza o config com os valores digitados na UI
        config.PALAVRAS_CHAVE = keywords
        config.LOCALIZACAO = location
        config.TIPO_VAGA = work_type

        driver = create_driver()
        bot = LinkedinBot(driver, status_queue, answer_queue, pause_event, stop_event, application_mode)
        bot.run()
    except Exception as e:
        error_msg = f"Um erro crítico ocorreu na thread do bot: {e}"
        logging.error(error_msg)
        status_queue.put(error_msg)
    finally:
        if driver:
            status_queue.put("O robô terminou. Você pode fechar o navegador manualmente.")
        status_queue.put("--- THREAD DO BOT ENCERRADA ---")

class ControlPanelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Painel de Controle do Robô")
        self.geometry("650x550")
        self.attributes('-topmost', True)

        self.bot_thread = None
        self.status_queue = queue.Queue()
        self.answer_queue = queue.Queue()
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        
        # Variáveis da interface
        self.application_mode_var = tk.StringVar(value="Todos")
        self.work_type_var = tk.StringVar(value="Todas")
        self.keywords_var = tk.StringVar(value=config.PALAVRAS_CHAVE)
        self.location_var = tk.StringVar(value=config.LOCALIZACAO)

        self._create_widgets()
        self.check_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _create_widgets(self):
        # Frame de Configurações
        settings_frame = tk.LabelFrame(self, text="Configurações da Busca", padx=10, pady=10)
        settings_frame.pack(pady=10, padx=10, fill=tk.X)

        # Palavras-chave
        tk.Label(settings_frame, text="Cargo / Palavras-chave:").grid(row=0, column=0, sticky='w', pady=2)
        self.entry_keywords = tk.Entry(settings_frame, textvariable=self.keywords_var, width=50)
        self.entry_keywords.grid(row=0, column=1, sticky='w', pady=2, padx=5)

        # Localização
        tk.Label(settings_frame, text="Localização:").grid(row=1, column=0, sticky='w', pady=2)
        self.entry_location = tk.Entry(settings_frame, textvariable=self.location_var, width=50)
        self.entry_location.grid(row=1, column=1, sticky='w', pady=2, padx=5)

        # Modalidade de trabalho
        tk.Label(settings_frame, text="Modalidade da vaga:").grid(row=2, column=0, sticky='w', pady=2)
        self.work_type_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.work_type_var,
            values=("Todas", "Presencial", "Híbrida", "Remota"),
            state="readonly",
            width=47,
        )
        self.work_type_combo.grid(row=2, column=1, sticky='w', pady=2, padx=5)

        # Tipo de candidatura
        tk.Label(settings_frame, text="Tipo de candidatura:").grid(row=3, column=0, sticky='w', pady=2)
        self.application_mode_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.application_mode_var,
            values=("Todos", "Apenas candidatura simplificada", "Candidatura por link de acesso"),
            state="readonly",
            width=47,
        )
        self.application_mode_combo.grid(row=3, column=1, sticky='w', pady=2, padx=5)

        # Frame de Controles
        control_frame = tk.Frame(self)
        control_frame.pack(pady=5, padx=10, fill=tk.X)

        self.start_button = tk.Button(control_frame, text="Iniciar", command=self.start_bot, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.pause_button = tk.Button(control_frame, text="Pausar", command=self.pause_bot, state=tk.DISABLED, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        self.resume_button = tk.Button(control_frame, text="Continuar", command=self.resume_bot, state=tk.DISABLED, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        self.stop_button = tk.Button(control_frame, text="Parar", command=self.stop_bot, state=tk.DISABLED, bg="#F44336", fg="white", font=("Arial", 10, "bold"))
        
        self.start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.pause_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.resume_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Terminal Visual (Log)
        self.log_text = scrolledtext.ScrolledText(self, wrap=tk.WORD, state=tk.DISABLED, bg="black", fg="#00FF00", font=("Consolas", 9))
        self.log_text.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)

    def check_and_start_chrome_debug(self) -> bool:
        self.update_log_visual("Verificando porta de depuração do Chrome (9222)...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 9222))
        sock.close()

        if result == 0:
            self.update_log_visual("Porta 9222 já está em uso. Assumindo que o Chrome já está rodando.")
            return True
        else:
            self.update_log_visual("Porta 9222 livre. Iniciando Chrome em modo de depuração...")
            command = f'"{config.CHROME_EXECUTABLE_PATH}" --remote-debugging-port=9222 --user-data-dir="{config.CHROME_DEBUG_PROFILE_PATH}"'
            try:
                subprocess.Popen(command, shell=True)
                self.update_log_visual("Comando para iniciar o Chrome executado. Aguardando 7 segundos...")
                time.sleep(7)
                return True
            except FileNotFoundError:
                error_msg = f"ERRO: Não foi possível encontrar 'chrome.exe'. Verifique o caminho em config.py:\n{config.CHROME_EXECUTABLE_PATH}"
                self.update_log_visual(error_msg)
                logging.error(error_msg)
                messagebox.showerror("Erro de Configuração", error_msg)
                return False
            except Exception as e:
                error_msg = f"ERRO ao iniciar o Chrome: {e}"
                self.update_log_visual(error_msg)
                logging.error(error_msg)
                messagebox.showerror("Erro Inesperado", error_msg)
                return False

    def start_bot(self):
        # Desabilita botões e campos de texto
        self.start_button.config(state=tk.DISABLED)
        self.application_mode_combo.config(state=tk.DISABLED)
        self.work_type_combo.config(state=tk.DISABLED)
        self.entry_keywords.config(state=tk.DISABLED)
        self.entry_location.config(state=tk.DISABLED)
        
        logging.info("Iniciando processo do Bot.")
        logging.info(f"Filtros - Palavras-chave: '{self.keywords_var.get()}', Localização: '{self.location_var.get()}'")

        if not self.check_and_start_chrome_debug():
            self.reset_ui()
            return

        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        
        self.pause_event.set()
        self.stop_event.clear()

        application_mode = {
            "Todos": "all",
            "Apenas candidatura simplificada": "easy",
            "Candidatura por link de acesso": "link",
        }[self.application_mode_var.get()]
        keywords = self.keywords_var.get()
        location = self.location_var.get()
        work_type = self.work_type_var.get()

        self.bot_thread = threading.Thread(
            target=bot_thread_worker,
            args=(self.status_queue, self.answer_queue, self.pause_event, self.stop_event, application_mode, keywords, location, work_type),
            daemon=True
        )
        self.bot_thread.start()

    def update_log_visual(self, message):
        """Atualiza apenas o terminal da interface."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def check_queue(self):
        try:
            message = self.status_queue.get_nowait()
            
            # Se for uma mensagem de erro ou aviso, salva no arquivo de log
            if "ERRO" in message or "FAIL" in message:
                logging.error(message)
            elif "AVISO" in message:
                logging.warning(message)
            elif not message.startswith("USER_INPUT_REQUIRED|"):
                logging.info(message) # Loga atividades normais no arquivo

            if message.startswith("USER_INPUT_REQUIRED|"):
                question = message.split("|", 1)[1]
                self.update_log_visual(f"AÇÃO NECESSÁRIA: O robô precisa da sua resposta para a pergunta: '{question}'")
                logging.warning(f"Intervenção manual solicitada: {question}")
                
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.DISABLED)
                answer = simpledialog.askstring("Pergunta do Recrutador", f"A automação encontrou uma pergunta que não sabe responder:\n\n'{question}'\n\nForneça sua resposta abaixo:")
                
                self.answer_queue.put(answer)
                if answer:
                    msg = f"Sua resposta '{answer}' foi enviada ao robô."
                    self.update_log_visual(msg)
                    logging.info(msg)
                else:
                    msg = "Você cancelou a pergunta. O robô irá pular a candidatura."
                    self.update_log_visual(msg)
                    logging.warning(msg)
                    
                if not self.stop_event.is_set():
                    self.pause_button.config(state=tk.NORMAL)
            else:
                self.update_log_visual(message)
                if "Aplicação pausada." in message:
                    self.pause_button.config(state=tk.DISABLED)
                    self.resume_button.config(state=tk.NORMAL)
                if "Aba externa fechada. Retomando automaticamente..." in message:
                    self.pause_button.config(state=tk.NORMAL)
                    self.resume_button.config(state=tk.DISABLED)
                if "--- THREAD DO BOT ENCERRADA ---" in message:
                    logging.info("Thread do bot encerrada.")
                    self.reset_ui()
        except queue.Empty:
            pass
        finally:
            self.after(200, self.check_queue)

    def pause_bot(self):
        logging.info("Bot pausado pelo usuário.")
        self.pause_event.clear()
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.NORMAL)

    def resume_bot(self):
        logging.info("Bot retomado pelo usuário.")
        self.pause_event.set()
        self.resume_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)

    def stop_bot(self):
        logging.warning("Bot parado pelo usuário.")
        self.stop_event.set()
        self.pause_event.set()
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        
    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.application_mode_combo.config(state="readonly")
        self.work_type_combo.config(state="readonly")
        self.entry_keywords.config(state=tk.NORMAL)
        self.entry_location.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

    def on_closing(self):
        if self.bot_thread and self.bot_thread.is_alive():
            if messagebox.askyesno("Sair", "O robô está em execução. Deseja pará-lo e sair?"):
                logging.warning("Aplicação encerrada com o robô em execução.")
                self.stop_event.set()
                self.pause_event.set()
                self.destroy()
        else:
            logging.info("Aplicação encerrada.")
            self.destroy()

if __name__ == "__main__":
    app = ControlPanelApp()
    app.mainloop()