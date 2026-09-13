from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings


class GigaChatSettingsTests(unittest.TestCase):
    def test_requires_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GIGACHAT_CREDENTIALS"):
                GigaChatSettings.from_environment()

    def test_rejects_tls_disable(self) -> None:
        with patch.dict(
            os.environ,
            {"GIGACHAT_CREDENTIALS": "synthetic-test-key", "GIGACHAT_VERIFY_SSL_CERTS": "false"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "TLS verification"):
                GigaChatSettings.from_environment()

    def test_rejects_unapproved_base_url(self) -> None:
        with patch.dict(
            os.environ,
            {"GIGACHAT_CREDENTIALS": "synthetic-test-key", "GIGACHAT_BASE_URL": "https://example.test"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "approved base URL"):
                GigaChatSettings.from_environment()

    def test_factory_passes_approved_configuration_without_logging_secret(self) -> None:
        received: dict[str, object] = {}

        def fake_sdk(**kwargs: object) -> object:
            received.update(kwargs)
            return object()

        settings = GigaChatSettings(credentials="synthetic-test-key")
        client = GigaChatClientFactory(constructor=fake_sdk).create(settings)

        self.assertIsNotNone(client)
        self.assertEqual(received["base_url"], "https://api.giga.chat/v1")
        self.assertTrue(received["verify_ssl_certs"])
        self.assertEqual(received["scope"], "GIGACHAT_API_PERS")

    def test_factory_constructs_installed_sdk_without_network_call(self) -> None:
        settings = GigaChatSettings(credentials="synthetic-test-key")
        client = GigaChatClientFactory().create(settings)

        self.assertEqual(client.__class__.__name__, "GigaChat")
        client.close()
