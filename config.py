"""Application settings. Personal values are loaded from the local .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _default_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LinkedInCopilot"
    return Path.home() / ".local" / "share" / "linkedin-copilot"


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else ROOT_DIR / path


DATA_DIR = _path_from_env("APP_DATA_DIR", _default_data_dir())
DEBUG_DIR = _path_from_env("APP_DEBUG_DIR", DATA_DIR / "debug")
LOG_DIR = _path_from_env("APP_LOG_DIR", DATA_DIR / "logs")
AI_PROFILE_FILE = _path_from_env("AI_PROFILE_FILE", DATA_DIR / "candidate_profile.txt")

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "").strip()
LINKEDIN_SENHA = os.getenv("LINKEDIN_SENHA", "")
CAMINHO_CURRICULO = os.getenv("CAMINHO_CURRICULO", "").strip()
AI_ENABLED = os.getenv("AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "sim"}
AI_PROFILE_CONTEXT = os.getenv("AI_PROFILE_CONTEXT", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "/zip/Qwen3.5-2B-Q8_0.gguf").strip()
AI_ALLOW_REMOTE = os.getenv("AI_ALLOW_REMOTE", "false").strip().lower() in {"1", "true", "yes", "sim"}
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "15"))
AI_REVIEW_PAUSE_SECONDS = max(0.0, float(os.getenv("AI_REVIEW_PAUSE_SECONDS", "2")))

PALAVRAS_CHAVE = os.getenv("PALAVRAS_CHAVE", "Analista de infraestrutura")
LOCALIZACAO = os.getenv("LOCALIZACAO", "Brasil")
TIPO_VAGA = os.getenv("TIPO_VAGA", "Todas")
LOCATIONS_KEYWORDS = [
    term.strip().lower()
    for term in os.getenv("LOCATIONS_KEYWORDS", "remoto,goiânia").split(",")
    if term.strip()
]

CHROME_EXECUTABLE_PATH = os.getenv(
    "CHROME_EXECUTABLE_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
CHROME_DEBUG_PROFILE_PATH = os.getenv("CHROME_DEBUG_PROFILE_PATH", r"C:\ChromeDebugProfile")

URL_LOGIN = "https://www.linkedin.com/login"
URL_BASE_VAGAS = "https://www.linkedin.com/jobs/search/"
URL_FEED = "https://www.linkedin.com/feed/"

ANSWERS_FILE = str(DATA_DIR / "answers.json")
SESSION_FILE = str(DATA_DIR / "linkedin_session.json")
APPLIED_JOBS_FILE = str(DATA_DIR / "applied_jobs.json")
LOG_FILE = str(LOG_DIR / "bot_execution.log")
PAUSE_FLAG_FILE = str(DATA_DIR / "pause.flag")
STOP_FLAG_FILE = str(DATA_DIR / "stop.flag")

DEFAULT_WAIT_SECONDS = float(os.getenv("SELENIUM_WAIT_SECONDS", "10"))
TRANSITION_WAIT_SECONDS = float(os.getenv("TRANSITION_WAIT_SECONDS", "5"))


def validate_runtime_config() -> None:
    missing = [
        name
        for name, value in (
            ("LINKEDIN_EMAIL", LINKEDIN_EMAIL),
            ("LINKEDIN_SENHA", LINKEDIN_SENHA),
            ("CAMINHO_CURRICULO", CAMINHO_CURRICULO),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Configuração obrigatória ausente no .env: " + ", ".join(missing)
        )


def ensure_runtime_dirs() -> None:
    for directory in (DATA_DIR, DEBUG_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
