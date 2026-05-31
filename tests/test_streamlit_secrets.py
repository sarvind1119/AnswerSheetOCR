import os
import unittest
from unittest.mock import patch

import app


class FakeSecrets:
    def get(self, key):
        values = {
            "OPENAI_API_KEY": "openai-secret",
            "SARVAM_API_KEY": "sarvam-secret",
            "OPENAI_TRUST_ENV_PROXY": False,
            "SARVAM_TRUST_ENV_PROXY": False,
        }
        return values.get(key)


class FakeStreamlit:
    secrets = FakeSecrets()


class StreamlitSecretsTests(unittest.TestCase):
    def test_load_streamlit_secrets_loads_both_provider_keys(self):
        with patch.object(app, "st", FakeStreamlit), patch.dict(os.environ, {}, clear=True):
            app.load_streamlit_secrets()

            self.assertEqual(os.environ["OPENAI_API_KEY"], "openai-secret")
            self.assertEqual(os.environ["SARVAM_API_KEY"], "sarvam-secret")
            self.assertEqual(os.environ["OPENAI_TRUST_ENV_PROXY"], "False")
            self.assertEqual(os.environ["SARVAM_TRUST_ENV_PROXY"], "False")


if __name__ == "__main__":
    unittest.main()
