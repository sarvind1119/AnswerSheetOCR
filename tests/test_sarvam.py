import json
import unittest
import zipfile

from answersheet_ocr.sarvam import (
    SARVAM_OUTPUT_FORMAT,
    batch_page_images,
    create_zip_batch,
    parse_sarvam_output_zip,
    split_question_blocks,
)
from tests.helpers import workspace_temp_dir


class SarvamTests(unittest.TestCase):
    def test_sarvam_output_format_is_api_supported(self):
        self.assertIn(SARVAM_OUTPUT_FORMAT, {"md", "html"})

    def test_batch_page_images(self):
        paths = [f"page_{index:03d}.png" for index in range(1, 26)]

        self.assertEqual([len(batch) for batch in batch_page_images(paths[:1])], [1])
        self.assertEqual([len(batch) for batch in batch_page_images(paths[:10])], [10])
        self.assertEqual([len(batch) for batch in batch_page_images(paths[:11])], [10, 1])
        self.assertEqual([len(batch) for batch in batch_page_images(paths)], [10, 10, 5])

    def test_create_zip_batch_is_flat(self):
        with workspace_temp_dir() as tmp_path:
            page_paths = []
            for index in range(1, 3):
                path = tmp_path / f"page_{index:03d}.png"
                path.write_bytes(b"image")
                page_paths.append(path)

            zip_path = create_zip_batch(page_paths, tmp_path / "zips", batch_index=1)

            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(archive.namelist(), ["page_001.png", "page_002.png"])

    def test_parse_sarvam_json_zip_to_pages(self):
        with workspace_temp_dir() as tmp_path:
            image_1 = tmp_path / "page_001.png"
            image_2 = tmp_path / "page_002.png"
            image_1.write_bytes(b"image")
            image_2.write_bytes(b"image")
            zip_path = tmp_path / "sarvam_output.zip"
            payload = {
                "pages": [
                    {
                        "page_number": 1,
                        "language": "hi-IN",
                        "blocks": [
                            {"text": "Q1. पहला उत्तर\nयह परीक्षण है।"},
                            {"text": "Q2. दूसरा उत्तर"},
                        ],
                    },
                    {
                        "page_number": 2,
                        "language": "en-IN",
                        "markdown": "1. English answer\nMore text",
                    },
                ]
            }
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("output.json", json.dumps(payload, ensure_ascii=False))

            pages = parse_sarvam_output_zip(
                zip_path,
                page_images=[image_1, image_2],
                language_code="hi-IN",
            )

            self.assertEqual(len(pages), 2)
            self.assertEqual(pages[0].page_number, 1)
            self.assertEqual(pages[0].image_path, str(image_1))
            self.assertEqual(pages[0].questions[0].question_number, "1")
            self.assertIn("पहला", pages[0].questions[0].raw_text)
            self.assertEqual(pages[1].detected_languages[0], "en-IN")

    def test_split_question_blocks_falls_back_to_uncertain_page_block(self):
        questions = split_question_blocks("No explicit question heading", page_number=3)

        self.assertEqual(len(questions), 1)
        self.assertIsNone(questions[0].question_number)
        self.assertTrue(questions[0].uncertainty_flags)


if __name__ == "__main__":
    unittest.main()
