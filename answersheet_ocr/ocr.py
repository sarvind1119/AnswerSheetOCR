from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from .config import env_flag, proxy_environment
from .models import PageOCR, answer_sheet_schema


OCR_INSTRUCTIONS = """You are digitizing handwritten Indian school exam answer sheets.

Extract handwritten text exactly as written. Preserve English, Hindi, Devanagari matras,
punctuation, line breaks where meaningful, bullets, underlines, margin notes, and visible
question numbering. Do not translate. Do not grade. If handwriting is unclear, include a
specific uncertainty flag instead of silently guessing. Return only structured data that
matches the supplied schema."""


def encode_image_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    mime_type = mime_type or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_json_text(response: Any) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text)

    if isinstance(response, dict):
        if response.get("output_text"):
            return str(response["output_text"])
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    fragments: list[str] = []
    for item in output or []:
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for part in content or []:
            if isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)
            if text:
                fragments.append(str(text))
    return "\n".join(fragments)


def parse_page_response(response: Any, *, page_number: int, image_path: Path) -> PageOCR:
    text = extract_json_text(response).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    payload = json.loads(text)
    payload["page_number"] = int(payload.get("page_number") or page_number)
    payload["image_path"] = str(image_path)
    page = PageOCR.model_validate(payload)

    for question in page.questions:
        if not question.page_refs:
            question.page_refs = [page.page_number]
    return page


class OpenAIOCRClient:
    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 120.0,
        trust_env_proxy: bool | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.trust_env_proxy = (
            env_flag("OPENAI_TRUST_ENV_PROXY", default=False)
            if trust_env_proxy is None
            else trust_env_proxy
        )

    def _client(self) -> Any:
        try:
            from openai import OpenAI
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI Python SDK is not installed. Run: pip install -r requirements.txt"
            ) from exc
        return OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=httpx.Client(
                timeout=self.timeout_seconds,
                trust_env=self.trust_env_proxy,
            ),
        )

    def ocr_page(self, image_path: Path, *, page_number: int) -> PageOCR:
        image_data_url = encode_image_data_url(image_path)
        response = self._client().responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"{OCR_INSTRUCTIONS}\n\n"
                                f"This is page {page_number}. Return page_number={page_number}."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": image_data_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "answer_sheet_page_ocr",
                    "strict": True,
                    "schema": answer_sheet_schema(),
                }
            },
        )
        return parse_page_response(response, page_number=page_number, image_path=image_path)


def describe_ocr_exception(exc: Exception) -> str:
    name = exc.__class__.__name__
    message = str(exc).strip() or "No additional error message was provided."

    if name == "APIConnectionError":
        proxy_vars = proxy_environment()
        if proxy_vars and not env_flag("OPENAI_TRUST_ENV_PROXY", default=False):
            return (
                "OpenAI connection failed. The app ignores environment proxy settings "
                "by default because this machine has proxy variables set. If your "
                "network requires a real proxy, set OPENAI_TRUST_ENV_PROXY=true and "
                "configure HTTP_PROXY/HTTPS_PROXY to a working proxy. "
                f"Original error: {message}"
            )
        return (
            "OpenAI connection failed. Check internet access, firewall/proxy settings, "
            f"and whether https://api.openai.com is reachable. Original error: {message}"
        )
    if name == "AuthenticationError":
        return "OpenAI authentication failed. Check OPENAI_API_KEY in .env."
    if name == "PermissionDeniedError":
        return "OpenAI denied access to this model or project. Check API project and model access."
    if name == "RateLimitError":
        return "OpenAI rate limit or quota was reached. Retry later or check billing/quota."
    if name == "BadRequestError":
        return f"OpenAI rejected the OCR request: {message}"
    if isinstance(exc, json.JSONDecodeError):
        return "OpenAI returned a response that was not valid JSON for the OCR schema."
    return f"{name}: {message}"
