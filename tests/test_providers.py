import unittest

from answersheet_ocr.ocr import OpenAIOCRClient
from answersheet_ocr.providers import OPENAI_PROVIDER, SARVAM_PROVIDER, create_ocr_client, provider_label
from answersheet_ocr.sarvam import SarvamOCRClient


class ProviderFactoryTests(unittest.TestCase):
    def test_create_openai_client(self):
        client = create_ocr_client(
            OPENAI_PROVIDER,
            openai_model="gpt-4o-mini",
            trust_env_proxy=False,
        )

        self.assertIsInstance(client, OpenAIOCRClient)
        self.assertEqual(client.model, "gpt-4o-mini")

    def test_create_sarvam_client(self):
        client = create_ocr_client(
            SARVAM_PROVIDER,
            openai_model="gpt-4o-mini",
            sarvam_language_code="en-IN",
        )

        self.assertIsInstance(client, SarvamOCRClient)
        self.assertEqual(client.language_code, "en-IN")

    def test_provider_label(self):
        self.assertEqual(provider_label(OPENAI_PROVIDER), "OpenAI")
        self.assertEqual(provider_label(SARVAM_PROVIDER), "Sarvam AI")


if __name__ == "__main__":
    unittest.main()
