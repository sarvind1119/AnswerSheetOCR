import json
import unittest
from pathlib import Path

from answersheet_ocr.ocr import parse_page_response
from tests.helpers import workspace_temp_dir


class FakeResponse:
    output_text = json.dumps(
        {
            "page_number": 1,
            "image_path": "",
            "detected_languages": ["English", "Hindi"],
            "questions": [
                {
                    "question_number": "Q1",
                    "raw_text": "Extracted answer",
                    "corrected_text": "",
                    "structure_elements": ["underlined heading"],
                    "margin_notes": [],
                    "uncertainty_flags": ["last word unclear"],
                    "page_refs": [],
                }
            ],
        }
)


class OcrParsingTests(unittest.TestCase):
    def test_parse_page_response_fills_image_path_and_page_refs(self):
        with workspace_temp_dir() as tmp_path:
            image_path = tmp_path / "page_001.png"
            image_path.write_bytes(b"fake")

            page = parse_page_response(FakeResponse(), page_number=1, image_path=image_path)

            self.assertEqual(page.page_number, 1)
            self.assertEqual(Path(page.image_path), image_path)
            self.assertEqual(page.questions[0].page_refs, [1])


if __name__ == "__main__":
    unittest.main()
