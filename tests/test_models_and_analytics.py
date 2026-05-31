import unittest

from answersheet_ocr.analytics import build_analytics
from answersheet_ocr.models import PageOCR, QuestionOCR, RunMetadata, RunRecord, answer_sheet_schema


class ModelsAndAnalyticsTests(unittest.TestCase):
    def test_schema_contains_required_ocr_fields(self):
        schema = answer_sheet_schema()
        self.assertEqual(
            schema["properties"]["questions"]["items"]["required"],
            [
                "question_number",
                "raw_text",
                "corrected_text",
                "structure_elements",
                "margin_notes",
                "uncertainty_flags",
                "page_refs",
            ],
        )

    def test_analytics_prefers_corrected_text(self):
        record = RunRecord(
            metadata=RunMetadata(
                run_id="run-1",
                source_pdf_name="sample.pdf",
                source_pdf_path="sample.pdf",
                model="gpt-4o-mini",
                dpi=220,
            ),
            page_images=["page_001.png"],
            pages=[
                PageOCR(
                    page_number=1,
                    image_path="page_001.png",
                    detected_languages=["English"],
                    questions=[
                        QuestionOCR(
                            question_number="1",
                            raw_text="short raw",
                            corrected_text="this corrected answer has five words",
                            uncertainty_flags=["word unclear"],
                            page_refs=[1],
                        ),
                        QuestionOCR(raw_text="unnumbered answer", page_refs=[1]),
                    ],
                )
            ],
        )

        analytics = build_analytics(record)

        self.assertEqual(analytics["page_count"], 1)
        self.assertEqual(analytics["question_count"], 2)
        self.assertEqual(analytics["uncertainty_count"], 1)
        self.assertEqual(analytics["missing_question_numbers"], 1)
        self.assertEqual(analytics["question_metrics"][0].word_count, 6)


if __name__ == "__main__":
    unittest.main()
