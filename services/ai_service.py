import os
from google import genai

class AIService:
    def __init__(self, api_key: str = None):
        # A chave pode vir do config.py ou de variáveis de ambiente
        self.client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
        
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
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"Erro ao consultar IA: {e}")
            return ""