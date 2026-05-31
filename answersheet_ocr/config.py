from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PAGES_DIR = DATA_DIR / "pages"
RUNS_DIR = DATA_DIR / "runs"
REPORTS_DIR = PROJECT_ROOT / "reports"
PROVIDER_ARTIFACTS_DIR = DATA_DIR / "provider_artifacts"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DPI = 220
DEFAULT_PROVIDER = "openai"
DEFAULT_SARVAM_LANGUAGE = "hi-IN"
SARVAM_OUTPUT_FORMAT = "md"
SARVAM_BATCH_SIZE = 10
SARVAM_LANGUAGES = {
    "Hindi": "hi-IN",
    "English": "en-IN",
    "Bengali": "bn-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Marathi": "mr-IN",
    "Odia": "or-IN",
    "Punjabi": "pa-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Urdu": "ur-IN",
    "Assamese": "as-IN",
    "Bodo": "bodo-IN",
    "Dogri": "doi-IN",
    "Kashmiri": "ks-IN",
    "Konkani": "kok-IN",
    "Maithili": "mai-IN",
    "Manipuri": "mni-IN",
    "Nepali": "ne-IN",
    "Sanskrit": "sa-IN",
    "Santali": "sat-IN",
    "Sindhi": "sd-IN",
}
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@dataclass(frozen=True)
class AppSettings:
    model: str = DEFAULT_MODEL
    dpi: int = DEFAULT_DPI
    poppler_path: str | None = None


def ensure_directories() -> None:
    for directory in (UPLOADS_DIR, PAGES_DIR, RUNS_DIR, REPORTS_DIR, PROVIDER_ARTIFACTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_dotenv(path: Path | None = None, *, override: bool = True) -> None:
    """Minimal .env loader to avoid making python-dotenv mandatory."""
    dotenv_path = path or PROJECT_ROOT / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def openai_api_key_available() -> bool:
    load_dotenv()
    return bool(os.getenv("OPENAI_API_KEY"))


def env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def proxy_environment() -> dict[str, str]:
    return {key: os.getenv(key, "") for key in PROXY_ENV_VARS if os.getenv(key)}
