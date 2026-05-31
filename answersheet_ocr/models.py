from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionOCR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_number: str | None = Field(
        default=None,
        description="Question number or label exactly as written, if visible.",
    )
    raw_text: str = Field(default="", description="Extracted answer text.")
    corrected_text: str = Field(default="", description="Human-reviewed correction.")
    structure_elements: list[str] = Field(default_factory=list)
    margin_notes: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    page_refs: list[int] = Field(default_factory=list)

    @property
    def review_text(self) -> str:
        return self.corrected_text.strip() or self.raw_text.strip()


class PageOCR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    image_path: str = ""
    detected_languages: list[str] = Field(default_factory=list)
    questions: list[QuestionOCR] = Field(default_factory=list)

    @field_validator("page_number")
    @classmethod
    def page_number_must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be positive")
        return value


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    source_pdf_name: str
    source_pdf_path: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model: str
    dpi: int


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: RunMetadata
    page_images: list[str] = Field(default_factory=list)
    pages: list[PageOCR] = Field(default_factory=list)

    def page_by_number(self, page_number: int) -> PageOCR | None:
        return next((page for page in self.pages if page.page_number == page_number), None)

    def image_for_page(self, page_number: int) -> Path | None:
        if 1 <= page_number <= len(self.page_images):
            return Path(self.page_images[page_number - 1])
        return None


def answer_sheet_schema() -> dict[str, Any]:
    """Strict JSON schema used for OpenAI structured page OCR output."""
    question_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question_number": {
                "type": ["string", "null"],
                "description": "Question number or visible label exactly as written.",
            },
            "raw_text": {
                "type": "string",
                "description": "Verbatim OCR text. Preserve all scripts and punctuation.",
            },
            "corrected_text": {
                "type": "string",
                "description": "Leave blank; reserved for human correction.",
            },
            "structure_elements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Bullets, underlines, headings, diagrams, or layout signals.",
            },
            "margin_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainty_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific notes for unclear handwriting or ambiguous symbols.",
            },
            "page_refs": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers supporting this question text.",
            },
        },
        "required": [
            "question_number",
            "raw_text",
            "corrected_text",
            "structure_elements",
            "margin_notes",
            "uncertainty_flags",
            "page_refs",
        ],
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "page_number": {"type": "integer"},
            "image_path": {
                "type": "string",
                "description": "Leave blank; the application fills this locally.",
            },
            "detected_languages": {
                "type": "array",
                "items": {"type": "string"},
            },
            "questions": {
                "type": "array",
                "items": question_schema,
            },
        },
        "required": ["page_number", "image_path", "detected_languages", "questions"],
    }
