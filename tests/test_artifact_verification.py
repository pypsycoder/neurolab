"""Repository evidence must be bounded metadata, never a raw-code trust shortcut."""

import json
import unittest

from neurolab.artifact_verification import (
    ArtifactVerificationError,
    JsonResponse,
    PublicRepositoryRequest,
    verify_public_repository,
)


SOURCE_KEY = "d" * 64
CLAIM_ID = "00000000-0000-0000-0000-000000000002"


def _transport(url: str) -> JsonResponse:
    if url.endswith("/repos/example/repro-kit"):
        return JsonResponse(json.dumps({
            "archived": False,
            "private": False,
            "default_branch": "main",
            "html_url": "https://github.com/example/repro-kit",
            "license": {"spdx_id": "MIT"},
        }).encode())
    if "/git/trees/main?recursive=1" in url:
        return JsonResponse(json.dumps({"truncated": False, "tree": [
            {"path": "README.md"}, {"path": "pyproject.toml"}, {"path": "tests/test_contract.py"}, {"path": "data/README.md"},
        ]}).encode())
    raise AssertionError(url)


class ArtifactVerificationTests(unittest.TestCase):
    def test_receipt_uses_metadata_signals_only(self):
        receipt = verify_public_repository(PublicRepositoryRequest(SOURCE_KEY, CLAIM_ID, "example/repro-kit"), transport=_transport)
        self.assertEqual(receipt.code_license, "MIT")
        self.assertTrue(receipt.has_readme)
        self.assertTrue(receipt.has_test_paths)
        self.assertTrue(receipt.has_environment_manifest)
        self.assertTrue(receipt.has_data_paths)
        self.assertEqual(len(receipt.evidence_sha256), 64)

    def test_invalid_repository_or_incomplete_tree_fails_closed(self):
        with self.assertRaises(ArtifactVerificationError):
            PublicRepositoryRequest(SOURCE_KEY, CLAIM_ID, "https://github.com/example/repro-kit")

        def truncated(url: str) -> JsonResponse:
            if url.endswith("/repos/example/repro-kit"):
                return _transport(url)
            return JsonResponse(json.dumps({"truncated": True, "tree": []}).encode())

        with self.assertRaisesRegex(ArtifactVerificationError, "incomplete"):
            verify_public_repository(PublicRepositoryRequest(SOURCE_KEY, CLAIM_ID, "example/repro-kit"), transport=truncated)
