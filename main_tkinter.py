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
from utils.privacy import sanitize_text

config.ensure_runtime_dirs()

# --- Configuração do Logging ---
logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8',
)

def bot_thread_worker(status_queue, answer_queue, pause_event, stop_event, application_mode, keywords, location, work_type, excluded_role_terms):
    """Função alvo da thread do robô."""
    driver = None
    try:
        # Atualiza o config com os valores digitados na UI
        config.PALAVRAS_CHAVE = keywords
        config.LOCALIZACAO = location
        config.TIPO_VAGA = work_type
        config.AI_EXCLUDED_ROLE_TERMS = tuple(excluded_role_terms)

        driver = create_driver()
        bot = LinkedinBot(driver, status_queue, answer_queue, pause_event, stop_event, application_mode)
        bot.run()
    except Exception as e:
        error_msg = f"Um erro crítico ocorreu na thread do bot: {sanitize_text(e)}"
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
        from services.ai_service import DEFAULT_EXCLUDED_ROLE_TERMS
        self.excluded_role_terms = tuple(
            config.AI_EXCLUDED_ROLE_TERMS
            if config.AI_EXCLUDED_ROLE_TERMS is not None
            else DEFAULT_EXCLUDED_ROLE_TERMS
        )
        self.excluded_terms_summary_var = tk.StringVar(
            value=f"{len(self.excluded_role_terms)} selecionados"
        )

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

        # Termos de cargos que a relevancia deve rejeitar
        tk.Label(settings_frame, text="Cargos a excluir:").grid(row=2, column=0, sticky='w', pady=2)
        self.excluded_terms_button = tk.Button(
            settings_frame,
            text="Selecionar termos...",
            command=self._select_excluded_role_terms,
        )
        self.excluded_terms_button.grid(row=2, column=1, sticky='w', pady=2, padx=5)
        tk.Label(settings_frame, textvariable=self.excluded_terms_summary_var).grid(
            row=2, column=1, sticky='w', padx=(125, 5)
        )

        # Modalidade de trabalho
        tk.Label(settings_frame, text="Modalidade da vaga:").grid(row=3, column=0, sticky='w', pady=2)
        self.work_type_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.work_type_var,
            values=("Todas", "Presencial", "Híbrida", "Remota"),
            state="readonly",
            width=47,
        )
        self.work_type_combo.grid(row=3, column=1, sticky='w', pady=2, padx=5)

        # Tipo de candidatura
        tk.Label(settings_frame, text="Tipo de candidatura:").grid(row=4, column=0, sticky='w', pady=2)
        self.application_mode_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.application_mode_var,
            values=("Todos", "Apenas candidatura simplificada", "Candidatura por link de acesso"),
            state="readonly",
            width=47,
        )
        self.application_mode_combo.grid(row=4, column=1, sticky='w', pady=2, padx=5)

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

    def _select_excluded_role_terms(self):
        from services.ai_service import DEFAULT_EXCLUDED_ROLE_TERMS

        dialog = tk.Toplevel(self)
        dialog.title("Selecionar cargos a excluir")
        dialog.geometry("520x480")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Selecione títulos que devem ser ignorados na avaliação de relevância.",
            wraplength=490,
        ).pack(padx=12, pady=(12, 6), anchor="w")
        list_frame = tk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set, exportselection=False)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        terms = list(dict.fromkeys((*DEFAULT_EXCLUDED_ROLE_TERMS, *self.excluded_role_terms)))
        selected = set(self.excluded_role_terms)
        for index, term in enumerate(terms):
            listbox.insert(tk.END, term)
            if term in selected:
                listbox.selection_set(index)

        actions = tk.Frame(dialog)
        actions.pack(fill=tk.X, padx=12, pady=(0, 12))
        tk.Button(actions, text="Selecionar todos", command=lambda: listbox.selection_set(0, tk.END)).pack(side=tk.LEFT)
        tk.Button(actions, text="Limpar", command=lambda: listbox.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=6)

        def apply_selection():
            self.excluded_role_terms = tuple(terms[index] for index in listbox.curselection())
            self.excluded_terms_summary_var.set(f"{len(self.excluded_role_terms)} selecionados")
            dialog.destroy()

        tk.Button(actions, text="Aplicar", command=apply_selection).pack(side=tk.RIGHT)

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
            try:
                subprocess.Popen([
                    config.CHROME_EXECUTABLE_PATH,
                    "--remote-debugging-port=9222",
                    f"--user-data-dir={config.CHROME_DEBUG_PROFILE_PATH}",
                ])
                self.update_log_visual("Aguardando o Chrome abrir a porta de depuração...")
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                        probe.settimeout(0.25)
                        if probe.connect_ex(("127.0.0.1", 9222)) == 0:
                            return True
                    time.sleep(0.2)
                self.update_log_visual("ERRO: O Chrome não abriu a porta de depuração dentro do limite.")
                return False
            except FileNotFoundError:
                error_msg = "ERRO: Não foi possível encontrar o Chrome. Confira CHROME_EXECUTABLE_PATH no .env."
                self.update_log_visual(error_msg)
                logging.error(error_msg)
                messagebox.showerror("Erro de Configuração", error_msg)
                return False
            except Exception as e:
                error_msg = f"ERRO ao iniciar o Chrome: {sanitize_text(e)}"
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
        self.excluded_terms_button.config(state=tk.DISABLED)
        
        logging.info("Iniciando processo do Bot.")
        logging.info("Filtros de busca configurados; valores omitidos do log.")

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
        excluded_role_terms = self.excluded_role_terms

        self.bot_thread = threading.Thread(
            target=bot_thread_worker,
            args=(self.status_queue, self.answer_queue, self.pause_event, self.stop_event, application_mode, keywords, location, work_type, excluded_role_terms),
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
                logging.error(sanitize_text(message))
            elif "AVISO" in message:
                logging.warning(sanitize_text(message))
            elif not message.startswith("USER_INPUT_REQUIRED|"):
                logging.info(sanitize_text(message))

            if message.startswith("USER_INPUT_REQUIRED|"):
                question = message.split("|", 1)[1]
                self.update_log_visual(f"AÇÃO NECESSÁRIA: O robô precisa da sua resposta para a pergunta: '{question}'")
                logging.warning(f"Intervenção manual solicitada: {sanitize_text(question)}")
                
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.DISABLED)
                answer = simpledialog.askstring("Pergunta do Recrutador", f"A automação encontrou uma pergunta que não sabe responder:\n\n'{question}'\n\nForneça sua resposta abaixo:")
                
                self.answer_queue.put(answer)
                if answer:
                    msg = "Sua resposta foi enviada ao robô."
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
        self.excluded_terms_button.config(state=tk.NORMAL)
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
