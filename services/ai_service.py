import config
import requests
from urllib.parse import urlsplit

class AIService:
    def __init__(self):
        self.llama_url = config.AI_BASE_URL
        self.profile_context = config.AI_PROFILE_CONTEXT

    def answer_question(self, question: str, options: list = None, profile_context: str = None) -> str:
        """
        Recebe a pergunta e opções (se for select/radio) e retorna a resposta exata.
        """
        profile_context = profile_context or self.profile_context
        if not config.AI_ENABLED or not profile_context or not options:
            return "UNSURE"
        try:
            endpoint = urlsplit(self.llama_url)
            local_hosts = {"localhost", "127.0.0.1", "::1"}
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                return "UNSURE"
            if endpoint.hostname.lower() not in local_hosts and not config.AI_ALLOW_REMOTE:
                return "UNSURE"
        except ValueError:
            return "UNSURE"
        prompt = (
            "Responda com o texto exato de uma opcao da lista, sem colchetes ou explicacoes. "
            "Use somente fatos do perfil fornecido. Se nao houver informacao suficiente, responda UNSURE.\n"
            f"Pergunta: {question}\nOpcoes: {options}"
        )
        try:
            response = requests.post(
                f"{self.llama_url}/chat/completions",
                json={
                    "model": config.AI_MODEL,
                    "messages": [
                        {"role": "system", "content": profile_context},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "max_tokens": 80
                },
                timeout=config.AI_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
            return "UNSURE" if answer.upper() == "UNSURE" else answer
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return ""
