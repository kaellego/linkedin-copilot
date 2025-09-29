# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- DADOS DO USUÁRIO ---
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_SENHA = os.getenv("LINKEDIN_SENHA")
CAMINHO_CURRICULO = os.getenv("CAMINHO_CURRICULO")
TELEFONE = "62981847446" # Coloque seu número aqui

# --- CONFIGURAÇÕES DE BUSCA ---
PALAVRAS_CHAVE = "Analista de infraestrutura"
LOCALIZACAO = "Brasil"
LOCATIONS_KEYWORDS = ["remoto", "goiânia"]

# --- CONFIGURAÇÕES DE AUTOMAÇÃO ---
# NOVO: Caminhos para a inicialização automática do Chrome em modo de depuração
# ATENÇÃO: Verifique se este é o caminho correto para o seu chrome.exe
CHROME_EXECUTABLE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_DEBUG_PROFILE_PATH = r"C:\ChromeDebugProfile" # Pasta para o perfil de automação

# --- URLs ---
URL_LOGIN = "https://www.linkedin.com/login"
URL_BASE_VAGAS = "https://www.linkedin.com/jobs/search/"
URL_FEED = "https://www.linkedin.com/feed/"

# --- ARQUIVOS DE CONTROLE ---
ANSWERS_FILE = "answers.json"
SESSION_FILE = "linkedin_session.json"
APPLIED_JOBS_FILE = "applied_jobs.json"

# --- Validações ---
if not all([LINKEDIN_EMAIL, LINKEDIN_SENHA, CAMINHO_CURRICULO]):
    raise ValueError("Por favor, defina LINKEDIN_EMAIL, LINKEDIN_SENHA e CAMINHO_CURRICULO no seu arquivo .env")