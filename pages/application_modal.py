# pages/application_modal.py
import time
import random
import threading
import json
import os
from queue import Queue
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
from pages.base_page import BasePage
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import config

class ApplicationModal(BasePage):
    """
    Representa e gerencia o modal de 'Candidatura Simplificada', agora com a
    capacidade de fechar a tela de confirmação final.
    """
    
    # --- Locators ---
    LIMIT_REACHED_ERROR = (By.XPATH, "//*[contains(text(), 'Você atingiu o limite de candidaturas simplificadas')]")
    MODAL_CONTENT = (By.CSS_SELECTOR, ".jobs-easy-apply-modal__content")
    FORM_GROUPS = (By.CSS_SELECTOR, ".fb-dash-form-element")
    NEXT_BUTTON = (By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
    REVIEW_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Revise sua candidatura']")
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "button[aria-label='Enviar candidatura']")
    UPLOAD_INPUT = (By.CSS_SELECTOR, 'input[type="file"]')
    
    # NOVO: Locator para o botão "Concluído" na tela de sucesso.
    DONE_BUTTON = (By.XPATH, "//button[contains(., 'Concluído')]")

    def __init__(self, driver: WebDriver, status_queue: Queue, answer_queue: Queue, pause_event: threading.Event, stop_event: threading.Event, answers_dict: dict):
        super().__init__(driver)
        self.status_queue = status_queue
        self.answer_queue = answer_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.answers = answers_dict

    def _normalize_question(self, text: str) -> str:
        return text.replace('*', '').strip().lower()

    def _check_control_signals(self):
        if self.stop_event.is_set():
            raise InterruptedError("Sinal de parada recebido.")
        if not self.pause_event.is_set():
            self.status_queue.put("Status: Pausado...")
            while not self.pause_event.is_set():
                resumed = self.pause_event.wait(timeout=15)
                if resumed: break
                try:
                    _ = self.driver.title
                    self.status_queue.put("(Mantendo a sessão ativa...)")
                except Exception as e:
                    self.status_queue.put(f"Erro no keep-alive: {e}.")
                if self.stop_event.is_set():
                    raise InterruptedError("Sinal de parada recebido durante a pausa.")
            self.status_queue.put("Status: Retomando...")

    def _save_answers(self):
        try:
            with open(config.ANSWERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.answers, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.status_queue.put(f"ERRO: Não foi possível salvar o arquivo de respostas: {e}")
            
    def process_application(self, curriculum_path: str) -> str:
        max_steps = 7
        for step in range(max_steps):
            self._check_control_signals()
            self.wait.until(EC.presence_of_element_located(self.MODAL_CONTENT))

            try:
                self.driver.find_element(*self.LIMIT_REACHED_ERROR)
                self.status_queue.put("Mensagem de limite de candidaturas detectada.")
                return "LIMIT_REACHED"
            except NoSuchElementException:
                pass

            try:
                form_groups = self.driver.find_elements(*self.FORM_GROUPS)
                for group in form_groups:
                    try:
                        label = group.find_element(By.TAG_NAME, "label")
                        question_text = label.text
                        if not question_text: continue
                        normalized_question = self._normalize_question(question_text)
                        
                        answer_to_apply = None
                        if normalized_question in self.answers:
                            answer_to_apply = self.answers[normalized_question]
                            self.status_queue.put(f"Usando resposta conhecida para: '{question_text}'")
                        else:
                            self.status_queue.put(f"USER_INPUT_REQUIRED|{question_text}")
                            user_answer = self.answer_queue.get()
                            if user_answer is None or user_answer.lower() == 'pular':
                                self.status_queue.put("Cancelando candidatura.")
                                return "FAIL"
                            self.answers[normalized_question] = user_answer
                            self._save_answers()
                            answer_to_apply = user_answer

                        if answer_to_apply is not None:
                            try:
                                select_el = group.find_element(By.TAG_NAME, "select")
                                Select(select_el).select_by_visible_text(answer_to_apply)
                                self.status_queue.put(f"Selecionado '{answer_to_apply}'.")
                            except NoSuchElementException:
                                input_el = group.find_element(By.TAG_NAME, "input")
                                if input_el.get_attribute('value') == '':
                                    input_el.send_keys(answer_to_apply)
                                    self.status_queue.put(f"Preenchido '{answer_to_apply}'.")
                    except NoSuchElementException: continue
            except Exception as e:
                self.status_queue.put(f"Erro ao processar perguntas: {e}")

            try:
                upload_field = self.driver.find_element(*self.UPLOAD_INPUT)
                if upload_field.is_displayed():
                    upload_field.send_keys(curriculum_path)
            except NoSuchElementException: pass

            try:
                self._click(self.SUBMIT_BUTTON)
                self.status_queue.put("Candidatura enviada com sucesso!")
                
                # MODIFICADO: Agora ele fecha a tela de confirmação
                self.status_queue.put("Aguardando tela de confirmação e fechando...")
                self._click(self.DONE_BUTTON)
                time.sleep(1) # Pequena pausa para o modal fechar completamente
                
                return "SUCCESS"
            except TimeoutException:
                self.status_queue.put(f"Etapa {step + 1}: Procurando 'Revisar' ou 'Avançar'...")
                try:
                    self._click(self.REVIEW_BUTTON)
                    self.status_queue.put("Indo para a tela de revisão...")
                    continue
                except TimeoutException:
                    try:
                        self._click(self.NEXT_BUTTON)
                        self.status_queue.put("Avançando para a próxima etapa.")
                        continue
                    except TimeoutException:
                        self.status_queue.put("ERRO: Não foi possível encontrar 'Enviar', 'Revisar' ou 'Avançar'.")
                        return "FAIL"
        
        self.status_queue.put("ERRO: Excedido o número máximo de etapas.")
        return "FAIL"