# main_tkinter.py
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog # Adicionado simpledialog
import threading
import queue
import time
from browser.driver_factory import create_driver
from bot.linkedin_bot import LinkedinBot

def bot_thread_worker(status_queue, answer_queue, pause_event, stop_event): # Adicionado answer_queue
    """Função alvo da thread do robô."""
    driver = None
    try:
        driver = create_driver()
        bot = LinkedinBot(driver, status_queue, answer_queue, pause_event, stop_event) # Passa answer_queue para o bot
        bot.run()
    except Exception as e:
        status_queue.put(f"Um erro crítico ocorreu na thread do bot: {e}")
    finally:
        if driver:
            driver.quit()
        status_queue.put("--- THREAD DO BOT ENCERRADA ---")

class ControlPanelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Painel de Controle do Robô")
        self.geometry("600x450") # Aumentei um pouco a altura
        self.attributes('-topmost', True)

        self.bot_thread = None
        self.status_queue = queue.Queue()
        self.answer_queue = queue.Queue() # Nova fila para respostas
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()

        self._create_widgets()
        self.check_queue()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _create_widgets(self):
        # ... (código dos botões e log como antes, sem alterações)
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10, fill=tk.X, padx=10)
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

    def update_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def check_queue(self):
        """Verifica a fila de status por novas mensagens ou perguntas."""
        try:
            message = self.status_queue.get_nowait()
            
            # LÓGICA MODIFICADA: Verifica se a mensagem é uma pergunta para o usuário
            if message.startswith("USER_INPUT_REQUIRED|"):
                question = message.split("|", 1)[1]
                self.update_log(f"AÇÃO NECESSÁRIA: O robô precisa da sua resposta para a pergunta: '{question}'")
                
                # Pausa a UI para o usuário não clicar em nada
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.DISABLED)

                # Abre a caixa de diálogo
                answer = simpledialog.askstring("Pergunta do Recrutador", f"A automação encontrou uma pergunta que não sabe responder:\n\n'{question}'\n\nForneça sua resposta abaixo:")
                
                # Envia a resposta (ou None se o usuário cancelar) de volta para o robô
                self.answer_queue.put(answer)
                
                if answer:
                    self.update_log(f"Sua resposta '{answer}' foi enviada ao robô.")
                else:
                    self.update_log("Você cancelou a pergunta. O robô irá pular a candidatura.")
                
                # Reativa o botão de pausa se o robô não estiver parado
                if not self.stop_event.is_set():
                    self.pause_button.config(state=tk.NORMAL)

            else: # Se for uma mensagem normal, apenas exibe no log
                self.update_log(message)
                if "--- THREAD DO BOT ENCERRADA ---" in message:
                    self.reset_ui()
        except queue.Empty:
            pass
        finally:
            self.after(200, self.check_queue) # Aumentei um pouco o tempo para 200ms

    def start_bot(self):
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        
        self.pause_event.set()
        self.stop_event.clear()

        # Passa a answer_queue para a thread
        self.bot_thread = threading.Thread(target=bot_thread_worker, args=(self.status_queue, self.answer_queue, self.pause_event, self.stop_event), daemon=True)
        self.bot_thread.start()

    # ... (o resto dos métodos da classe permanecem os mesmos)
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
        # Se o bot estiver pausado esperando uma resposta, precisamos "desbloqueá-lo"
        if not self.pause_event.is_set():
            self.pause_event.set()
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)

    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

    def on_closing(self):
        if self.bot_thread and self.bot_thread.is_alive():
            if messagebox.askyesno("Sair", "O robô está em execução. Deseja pará-lo e sair?"):
                self.stop_event.set()
                if not self.pause_event.is_set():
                    self.pause_event.set()
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":
    app = ControlPanelApp()
    app.mainloop()