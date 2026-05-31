import unittest

from answersheet_ocr.models import RunRecord


class BackwardCompatibilityTests(unittest.TestCase):
    def test_old_run_metadata_without_provider_fields_still_loads(self):
        record = RunRecord.model_validate(
            {
                "metadata": {
                    "run_id": "old-run",
                    "source_pdf_name": "old.pdf",
                    "source_pdf_path": "data/uploads/old.pdf",
                    "created_at": "2026-05-31T00:00:00+00:00",
                    "model": "gpt-4o-mini",
                    "dpi": 220,
                },
                "page_images": [],
                "pages": [],
            }
        )

        self.assertEqual(record.metadata.ocr_provider, "openai")
        self.assertIsNone(record.metadata.sarvam_language_code)
        self.assertEqual(record.metadata.provider_job_ids, [])


if __name__ == "__main__":
    unittest.main()
