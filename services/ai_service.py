from google import genai
import config
import requests

class AIService:
    def __init__(self, api_key: str = None):


        # Usando o servidor llama.cpp em vez do cliente Gemini
        self.llama_url = "http://10.0.0.1:8080/v1"
        # Resumo do seu perfil profissional para a IA usar como base
        self.profile_context = """
        Você é um assistente que responde formulários de candidatura no LinkedIn em primeira pessoa.
        Responda de forma direta, concisa e objetiva.
        
        Dados do candidato:
        - Nome: [Seu Nome]
        - Experiência: Administrador de Redes, Infraestrutura, Python, Docker, Linux, Suporte de TI.
        - Tempo de experiência geral: 5+ anos.
        - Nível de inglês: Intermediário / Avançado.
        - Salário pretendido: A combinar / Aberto a propostas.
        - Disponibilidade: Imediata.
        - CNH: B.
        """

    def answer_question(self, question: str, options: list = None) -> str:
        """
        Recebe a pergunta e opções (se for select/radio) e retorna a resposta exata.
        """
        prompt = f"""
        {self.profile_context}

        Pergunta do recrutador: "{question}"
        """
        
        if options:
            prompt += f"\nOpções disponíveis: {options}\nEscolha estritamente UMA das opções acima que melhor represente o candidato."
        else:
            prompt += "\nSe for uma pergunta numérica (ex: anos de experiência), responda apenas com o número inteiro. Se for sim/não, responda apenas 'Sim' ou 'Não'."

        try:





            # Enviando a requisição para o servidor llama.cpp
            response = requests.post(
                f"{self.llama_url}/chat/completions",
                json={
                    "model": "llama3",
                    "messages": [
                        {"role": "system", "content": self.profile_context},
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150
                }
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Erro ao consultar IA: {e}")
            return ""