from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .config import PROVIDER_ARTIFACTS_DIR, SARVAM_BATCH_SIZE, SARVAM_OUTPUT_FORMAT, env_flag
from .models import PageOCR, QuestionOCR


QUESTION_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:q(?:uestion)?\.?\s*)?(\d+[A-Za-z]?|[A-Za-z])[\).:\-]\s+"
)


class SarvamOCRError(RuntimeError):
    """Raised for Sarvam OCR integration failures."""


def batch_page_images(
    image_paths: Iterable[Path | str],
    *,
    batch_size: int = SARVAM_BATCH_SIZE,
) -> list[list[Path]]:
    paths = [Path(path) for path in image_paths]
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    return [paths[index : index + batch_size] for index in range(0, len(paths), batch_size)]


def create_zip_batch(page_paths: list[Path], output_dir: Path, *, batch_index: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"sarvam_batch_{batch_index:03d}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for page_path in page_paths:
            archive.write(page_path, arcname=page_path.name)
    return zip_path


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_text_from_value(item) for item in value]
        return "\n".join(part for part in parts if part.strip())
    if isinstance(value, dict):
        for key in ("text", "content", "markdown", "md", "html"):
            if key in value:
                text = _text_from_value(value[key])
                if text.strip():
                    return text
        parts = [_text_from_value(item) for item in value.values()]
        return "\n".join(part for part in parts if part.strip())
    return ""


def _page_number_from_payload(payload: dict[str, Any], fallback: int) -> int:
    for key in ("page_number", "page", "page_index"):
        value = payload.get(key)
        if isinstance(value, int):
            return value + 1 if key == "page_index" and value == fallback - 1 else value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return fallback


def split_question_blocks(text: str, *, page_number: int) -> list[QuestionOCR]:
    matches = list(QUESTION_HEADING_RE.finditer(text))
    if not matches:
        return [
            QuestionOCR(
                question_number=None,
                raw_text=text.strip(),
                uncertainty_flags=["Question boundaries were not explicit in Sarvam output."],
                page_refs=[page_number],
            )
        ]

    questions: list[QuestionOCR] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        questions.append(
            QuestionOCR(
                question_number=match.group(1),
                raw_text=block,
                structure_elements=["Sarvam preserved layout text block"],
                page_refs=[page_number],
            )
        )
    return questions


def page_ocr_from_sarvam_payload(
    payload: dict[str, Any],
    *,
    fallback_page_number: int,
    image_path: Path | None = None,
    language_code: str | None = None,
) -> PageOCR:
    page_number = _page_number_from_payload(payload, fallback_page_number)

    questions: list[QuestionOCR] = []
    raw_questions = payload.get("questions")
    if isinstance(raw_questions, list):
        for item in raw_questions:
            if isinstance(item, dict):
                text = _text_from_value(item).strip()
                if text:
                    questions.append(
                        QuestionOCR(
                            question_number=(
                                item.get("question_number")
                                or item.get("question")
                                or item.get("label")
                            ),
                            raw_text=text,
                            structure_elements=["Sarvam structured question block"],
                            page_refs=[page_number],
                        )
                    )

    if not questions:
        blocks = payload.get("blocks")
        if isinstance(blocks, list):
            text = "\n".join(_text_from_value(block) for block in blocks).strip()
        else:
            text = _text_from_value(payload).strip()
        if text:
            questions = split_question_blocks(text, page_number=page_number)

    if not questions:
        questions = [
            QuestionOCR(
                question_number=None,
                raw_text="",
                uncertainty_flags=["Sarvam output did not contain parseable text for this page."],
                page_refs=[page_number],
            )
        ]

    languages = []
    for key in ("detected_languages", "languages", "language"):
        value = payload.get(key)
        if isinstance(value, list):
            languages.extend(str(item) for item in value)
        elif isinstance(value, str):
            languages.append(value)
    if language_code and language_code not in languages:
        languages.append(language_code)

    return PageOCR(
        page_number=page_number,
        image_path=str(image_path or ""),
        detected_languages=languages,
        questions=questions,
    )


def _find_page_payloads(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("pages", "page_data", "page_results"):
            pages = value.get(key)
            if isinstance(pages, list):
                return [page for page in pages if isinstance(page, dict)]
        if any(key in value for key in ("page_number", "page", "blocks", "text", "content", "markdown")):
            return [value]
        found: list[dict[str, Any]] = []
        for item in value.values():
            found.extend(_find_page_payloads(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(_find_page_payloads(item))
        return found
    return []


def parse_sarvam_output_zip(
    zip_path: Path,
    *,
    page_images: list[Path],
    language_code: str,
) -> list[PageOCR]:
    if not zip_path.exists():
        raise SarvamOCRError(f"Sarvam output ZIP not found: {zip_path}")

    pages: list[PageOCR] = []
    with zipfile.ZipFile(zip_path) as archive:
        json_names = [name for name in archive.namelist() if name.lower().endswith(".json")]
        md_names = [name for name in archive.namelist() if name.lower().endswith(".md")]
        if json_names:
            for json_name in json_names:
                payload = json.loads(archive.read(json_name).decode("utf-8"))
                page_payloads = _find_page_payloads(payload)
                for offset, page_payload in enumerate(page_payloads, start=1):
                    fallback_page = len(pages) + 1
                    image = page_images[fallback_page - 1] if fallback_page <= len(page_images) else None
                    pages.append(
                        page_ocr_from_sarvam_payload(
                            page_payload,
                            fallback_page_number=fallback_page,
                            image_path=image,
                            language_code=language_code,
                        )
                    )
        elif md_names:
            for fallback_page, md_name in enumerate(sorted(md_names), start=1):
                image = page_images[fallback_page - 1] if fallback_page <= len(page_images) else None
                pages.append(
                    page_ocr_from_sarvam_payload(
                        {"page_number": fallback_page, "markdown": archive.read(md_name).decode("utf-8")},
                        fallback_page_number=fallback_page,
                        image_path=image,
                        language_code=language_code,
                    )
                )
        else:
            raise SarvamOCRError("Sarvam output ZIP did not include JSON or Markdown output.")

    for index, page in enumerate(sorted(pages, key=lambda item: item.page_number), start=1):
        if index <= len(page_images):
            page.image_path = str(page_images[index - 1])
    return sorted(pages, key=lambda item: item.page_number)


class SarvamOCRClient:
    def __init__(
        self,
        *,
        language_code: str = "hi-IN",
        output_format: str = SARVAM_OUTPUT_FORMAT,
        timeout_seconds: float = 600.0,
        trust_env_proxy: bool | None = None,
    ) -> None:
        self.language_code = language_code
        self.output_format = output_format
        self.timeout_seconds = timeout_seconds
        self.trust_env_proxy = (
            env_flag("SARVAM_TRUST_ENV_PROXY", default=False)
            if trust_env_proxy is None
            else trust_env_proxy
        )
        self.job_ids: list[str] = []

    def _client(self) -> Any:
        try:
            from sarvamai import SarvamAI
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "The Sarvam AI Python SDK is not installed. Run: pip install -r requirements.txt"
            ) from exc
        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise SarvamOCRError("SARVAM_API_KEY is missing. Add it to .env or Streamlit secrets.")
        return SarvamAI(
            api_subscription_key=api_key,
            timeout=self.timeout_seconds,
            httpx_client=httpx.Client(
                timeout=self.timeout_seconds,
                trust_env=self.trust_env_proxy,
            ),
        )

    def ocr_pages(self, page_images: list[Path | str], *, run_id: str) -> list[PageOCR]:
        image_paths = [Path(path) for path in page_images]
        artifact_dir = PROVIDER_ARTIFACTS_DIR / run_id / "sarvam"
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        pages: list[PageOCR] = []
        client = self._client()
        for batch_index, batch in enumerate(batch_page_images(image_paths), start=1):
            zip_path = create_zip_batch(batch, artifact_dir, batch_index=batch_index)
            output_zip = artifact_dir / f"sarvam_output_{batch_index:03d}.zip"
            job = client.document_intelligence.create_job(
                language=self.language_code,
                output_format=self.output_format,
            )
            job_id = str(getattr(job, "job_id", ""))
            if job_id:
                self.job_ids.append(job_id)
            job.upload_file(str(zip_path))
            job.start()
            status = job.wait_until_complete()
            state = str(getattr(status, "job_state", ""))
            if state not in {"Completed", "PartiallyCompleted"}:
                raise SarvamOCRError(f"Sarvam job {job_id or batch_index} failed with state: {state}")
            job.download_output(str(output_zip))
            batch_pages = parse_sarvam_output_zip(
                output_zip,
                page_images=batch,
                language_code=self.language_code,
            )
            page_offset = (batch_index - 1) * SARVAM_BATCH_SIZE
            for page in batch_pages:
                if page.page_number <= len(batch):
                    page.page_number = page_offset + page.page_number
                if 1 <= page.page_number <= len(image_paths):
                    page.image_path = str(image_paths[page.page_number - 1])
                for question in page.questions:
                    question.page_refs = [page.page_number]
            pages.extend(batch_pages)

        return sorted(pages, key=lambda item: item.page_number)


def describe_sarvam_exception(exc: Exception) -> str:
    name = exc.__class__.__name__
    message = str(exc).strip() or "No additional error message was provided."
    status_code = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    details = f"{message} {body or ''}".strip()

    if status_code in {401, 403} or "invalid_api_key" in details:
        return "Sarvam authentication failed. Check SARVAM_API_KEY in .env or Streamlit secrets."
    if status_code == 429 or "quota" in details.lower() or "rate" in details.lower():
        return "Sarvam rate limit or quota was reached. Retry later or check Sarvam credits."
    if status_code == 422 or "max_page_limit_exceeded" in details:
        return "Sarvam rejected the document. Check file format, page count, or corrupted input."
    if isinstance(exc, SarvamOCRError):
        return str(exc)
    return f"{name}: {message}"
