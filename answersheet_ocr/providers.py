from __future__ import annotations

from .ocr import OpenAIOCRClient
from .sarvam import SarvamOCRClient


OPENAI_PROVIDER = "openai"
SARVAM_PROVIDER = "sarvam"
PROVIDER_LABELS = {
    OPENAI_PROVIDER: "OpenAI",
    SARVAM_PROVIDER: "Sarvam AI",
}


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider)


def create_ocr_client(
    provider: str,
    *,
    openai_model: str,
    trust_env_proxy: bool = False,
    sarvam_language_code: str | None = None,
):
    if provider == OPENAI_PROVIDER:
        return OpenAIOCRClient(model=openai_model, trust_env_proxy=trust_env_proxy)
    if provider == SARVAM_PROVIDER:
        return SarvamOCRClient(
            language_code=sarvam_language_code or "hi-IN",
            trust_env_proxy=trust_env_proxy,
        )
    raise ValueError(f"Unsupported OCR provider: {provider}")
