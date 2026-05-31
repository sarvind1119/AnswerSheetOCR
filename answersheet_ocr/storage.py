from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import PAGES_DIR, RUNS_DIR, UPLOADS_DIR, ensure_directories
from .models import PageOCR, RunMetadata, RunRecord


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return value or "answer-sheet"


def new_run_id(source_name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(Path(source_name).stem)[:40]}-{uuid4().hex[:8]}"


def save_uploaded_pdf(uploaded_file, *, run_id: str) -> Path:
    ensure_directories()
    upload_dir = UPLOADS_DIR / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / slugify(uploaded_file.name)
    target.write_bytes(uploaded_file.getbuffer())
    return target


def copy_pdf_to_uploads(pdf_path: Path, *, run_id: str) -> Path:
    ensure_directories()
    upload_dir = UPLOADS_DIR / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / slugify(pdf_path.name)
    shutil.copy2(pdf_path, target)
    return target


def page_output_dir(run_id: str) -> Path:
    return PAGES_DIR / run_id


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def create_run_record(
    *,
    run_id: str,
    source_pdf_name: str,
    source_pdf_path: Path,
    model: str,
    dpi: int,
    page_images: list[Path],
) -> RunRecord:
    return RunRecord(
        metadata=RunMetadata(
            run_id=run_id,
            source_pdf_name=source_pdf_name,
            source_pdf_path=str(source_pdf_path),
            model=model,
            dpi=dpi,
        ),
        page_images=[str(path) for path in page_images],
        pages=[],
    )


def load_run(run_id: str) -> RunRecord:
    payload = json.loads(run_path(run_id).read_text(encoding="utf-8"))
    return RunRecord.model_validate(payload)


def save_run(record: RunRecord) -> Path:
    ensure_directories()
    target = run_path(record.metadata.run_id)
    target.write_text(
        json.dumps(record.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def upsert_page(record: RunRecord, page: PageOCR) -> RunRecord:
    pages = [existing for existing in record.pages if existing.page_number != page.page_number]
    pages.append(page)
    pages.sort(key=lambda item: item.page_number)
    record.pages = pages
    return record
