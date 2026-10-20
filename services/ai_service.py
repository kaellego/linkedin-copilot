import config
import requests
import unicodedata
from urllib.parse import urlsplit

class AIService:
    def __init__(self):
        self.llama_url = config.AI_BASE_URL
        self.profile_context = config.AI_PROFILE_CONTEXT

    def answer_question(self, question: str, options: list = None, profile_context: str = None, field_type: str = "text") -> str:
        """
        Recebe a pergunta e opções (se for select/radio) e retorna a resposta exata.
        """
        profile_context = profile_context or self.profile_context
        if not config.AI_ENABLED or not profile_context:
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
        if options:
            prompt = (
                "Responda com o texto exato de uma opcao da lista, sem explicacoes. "
                "Use somente fatos do perfil. Se nao houver informacao suficiente, responda UNSURE.\n"
                f"Pergunta: {question}\nOpcoes: {options}"
            )
            max_tokens = 80
        else:
            numeric_rule = (
                "O campo aceita somente um valor numerico; responda apenas com algarismos, "
                "sem palavras, unidade ou explicacao.\n"
                if field_type == "numeric" else ""
            )
            prompt = (
                "Responda a pergunta em portugues, em uma frase curta (ate 300 caracteres), "
                "em primeira pessoa quando apropriado. Use somente fatos do perfil fornecido. "
                "Pode estimar duracoes a partir de datas, identificando-as como aproximadas. "
                "Nao invente fatos, nao inclua dados de contato e nao repita a pergunta. "
                f"Tipo de campo: {field_type}.\n{numeric_rule}"
                "Se nao houver base suficiente, responda exatamente UNSURE.\n"
                f"Pergunta: {question}"
            )
            max_tokens = 120
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
                    "max_tokens": max_tokens
                },
                timeout=config.AI_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
            return "UNSURE" if answer.upper() == "UNSURE" else answer
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return ""

    def assess_job_relevance(self, job_title: str, target_keywords: str) -> bool | None:
        """Classify title relevance; None means uncertain or unavailable."""
        if not config.AI_ENABLED or not job_title.strip() or not target_keywords.strip():
            return None
        try:
            endpoint = urlsplit(self.llama_url)
            local_hosts = {"localhost", "127.0.0.1", "::1"}
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                return None
            if endpoint.hostname.lower() not in local_hosts and not config.AI_ALLOW_REMOTE:
                return None
        except ValueError:
            return None

        prompt = (
            f"Analise o título da vaga e compare-o com as palavras-chave alvo: '{target_keywords.strip()[:500]}'\n"
            "Considere variações de senioridade (junior, analista, gerente), sinônimos e contextos operacionais."
            "Ignore empresa, local e benefícios. Responda apenas SIM se a função pertencer claramente à mesma "
            "área de TI, NAO se for uma área diferente, ou INCERTO se não houver informação suficiente para decidir"
            "O foco é verificar a semelhança profissional da área de atuação."
            #"Avalie somente a semelhanca profissional entre o titulo da vaga e o cargo/palavras-chave alvo. "
            #"Considere sinonimos e variacoes de senioridade; ignore empresa, local e beneficios. "
            #"Responda somente SIM se a funcao for claramente da mesma area, NAO se for diferente, "
            #"ou INCERTO se o titulo nao permitir decidir.\n"
            #f"Cargo/palavras-chave alvo: {target_keywords.strip()[:500]}\n"
            f"Titulo da vaga: {job_title.strip()[:300]}"
        )
        try:
            response = requests.post(
                f"{self.llama_url}/chat/completions",
                json={"model": config.AI_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0, "max_tokens": 8},
                timeout=min(config.AI_TIMEOUT_SECONDS, 4),
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip().upper().strip(" .")
            answer = unicodedata.normalize("NFKD", answer).encode("ascii", "ignore").decode("ascii")
            if answer in {"SIM", "YES"}:
                return True
            if answer in {"NAO", "NO"}:
                return False
            return None
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None
