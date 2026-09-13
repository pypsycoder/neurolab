from __future__ import annotations

import os
import unittest

from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings


@unittest.skipUnless(
    os.environ.get("RUN_GIGACHAT_LIVE") == "1",
    "Set RUN_GIGACHAT_LIVE=1 explicitly to run a live GigaChat check.",
)
class GigaChatLiveIntegrationTests(unittest.TestCase):
    def test_authenticated_models_request(self) -> None:
        settings = GigaChatSettings.from_environment()
        with GigaChatClientFactory().create(settings) as client:
            models = client.get_models()

        self.assertTrue(models.data, "GigaChat returned no available models")
