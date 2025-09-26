# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Carrega as variáveis do arquivo .env
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_SENHA = os.getenv("LINKEDIN_SENHA")
CAMINHO_CURRICULO = os.getenv("CAMINHO_CURRICULO")
TELEFONE = "62981847446" # Coloque seu número aqui

# Configurações de busca
PALAVRAS_CHAVE = "Analista de infraestrutura"
LOCALIZACAO = "Brasil"

# NOVO: Lista de palavras-chave para filtrar a localização das vagas.
# O bot se candidatará se a localização da vaga contiver QUALQUER um desses termos.
# Use letras minúsculas.
LOCATIONS_KEYWORDS = ["remoto", "goiânia"]

# URLs
URL_LOGIN = "https://www.linkedin.com/login"
URL_BASE_VAGAS = "https://www.linkedin.com/jobs/search/"
URL_FEED = "https://www.linkedin.com/feed/"

# Arquivos de controle
SESSION_FILE = "linkedin_session.json"
ANSWERS_FILE = "answers.json"
PAUSE_FLAG_FILE = "pause.flag"
STOP_FLAG_FILE = "stop.flag"

# Validações simples
if not all([LINKEDIN_EMAIL, LINKEDIN_SENHA, CAMINHO_CURRICULO]):
    raise ValueError("Por favor, defina LINKEDIN_EMAIL, LINKEDIN_SENHA e CAMINHO_CURRICULO no seu arquivo .env")