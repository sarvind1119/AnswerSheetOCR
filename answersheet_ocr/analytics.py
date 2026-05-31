from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import RunRecord


@dataclass(frozen=True)
class QuestionMetric:
    page_number: int
    question_number: str
    word_count: int
    uncertainty_count: int


def count_words(text: str) -> int:
    return len([token for token in text.split() if token.strip()])


def build_analytics(record: RunRecord) -> dict:
    languages: Counter[str] = Counter()
    question_metrics: list[QuestionMetric] = []
    uncertainty_count = 0
    missing_question_numbers = 0

    for page in record.pages:
        languages.update(page.detected_languages)
        for index, question in enumerate(page.questions, start=1):
            text = question.review_text
            uncertainty_count += len(question.uncertainty_flags)
            label = question.question_number or f"Page {page.page_number} Q{index}"
            if not question.question_number:
                missing_question_numbers += 1
            question_metrics.append(
                QuestionMetric(
                    page_number=page.page_number,
                    question_number=label,
                    word_count=count_words(text),
                    uncertainty_count=len(question.uncertainty_flags),
                )
            )

    return {
        "page_count": len(record.page_images),
        "ocr_page_count": len(record.pages),
        "question_count": len(question_metrics),
        "detected_languages": dict(languages),
        "uncertainty_count": uncertainty_count,
        "missing_question_numbers": missing_question_numbers,
        "question_metrics": question_metrics,
    }
