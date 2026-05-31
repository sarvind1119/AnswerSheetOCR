import unittest

from answersheet_ocr.models import PageOCR, RunMetadata, RunRecord
from answersheet_ocr.storage import upsert_page


class StorageTests(unittest.TestCase):
    def test_upsert_page_replaces_existing_page(self):
        record = RunRecord(
            metadata=RunMetadata(
                run_id="storage-test",
                source_pdf_name="sample.pdf",
                source_pdf_path="sample.pdf",
                model="gpt-4o-mini",
                dpi=220,
            ),
            page_images=["page_001.png"],
            pages=[
                PageOCR(page_number=1, image_path="old.png", detected_languages=["English"])
            ],
        )

        updated = upsert_page(
            record,
            PageOCR(page_number=1, image_path="new.png", detected_languages=["Hindi"]),
        )

        self.assertEqual(len(updated.pages), 1)
        self.assertEqual(updated.pages[0].image_path, "new.png")
        self.assertEqual(updated.pages[0].detected_languages, ["Hindi"])


if __name__ == "__main__":
    unittest.main()
