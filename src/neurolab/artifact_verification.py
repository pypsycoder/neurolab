"""Bounded public GitHub repository evidence for an already reviewed claim."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
_MAX_RESPONSE_BYTES = 1_000_000


class ArtifactVerificationError(RuntimeError):
    """A public repository cannot be used as reproducibility evidence."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise ArtifactVerificationError("repository API redirect was rejected")


@dataclass(frozen=True)
class PublicRepositoryRequest:
    source_key: str
    claim_id: str
    repository: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise ArtifactVerificationError("source key is malformed")
        try:
            UUID(self.claim_id)
        except ValueError as error:
            raise ArtifactVerificationError("claim id is malformed") from error
        if not _REPOSITORY.fullmatch(self.repository):
            raise ArtifactVerificationError("repository must be an owner/name identifier")


@dataclass(frozen=True)
class JsonResponse:
    payload: bytes


@dataclass(frozen=True)
class PublicArtifactReceipt:
    source_key: str
    claim_id: str
    repository: str
    api_url: str
    html_url: str
    default_branch: str
    code_license: str
    evidence_sha256: str
    has_readme: bool
    has_test_paths: bool
    has_environment_manifest: bool
    has_data_paths: bool
    verification_status: str = "public_artifact_metadata_verified"


def _api_url(path: str) -> str:
    return f"https://api.github.com{path}"


def default_github_transport(url: str) -> JsonResponse:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ArtifactVerificationError("repository API target is outside the allowlist")
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "neurolab-artifact-verification/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=20) as response:
            if response.geturl() != url:
                raise ArtifactVerificationError("repository API location changed")
            payload = response.read(_MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ArtifactVerificationError("repository API request failed") from error
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise ArtifactVerificationError("repository API response exceeds the size limit")
    return JsonResponse(payload=payload)


def _json(response: JsonResponse) -> dict[str, object]:
    try:
        payload = json.loads(response.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactVerificationError("repository API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ArtifactVerificationError("repository API envelope is invalid")
    return payload


def verify_public_repository(
    request: PublicRepositoryRequest,
    *,
    transport: Callable[[str], JsonResponse] = default_github_transport,
) -> PublicArtifactReceipt:
    """Verify public-code signals; source/repository linkage is enforced by storage."""
    repository_url = _api_url(f"/repos/{request.repository}")
    metadata = _json(transport(repository_url))
    branch = metadata.get("default_branch")
    html_url = metadata.get("html_url")
    license_data = metadata.get("license")
    if metadata.get("archived") is True or metadata.get("private") is True:
        raise ArtifactVerificationError("repository is not an active public artifact")
    if not isinstance(branch, str) or not _BRANCH.fullmatch(branch):
        raise ArtifactVerificationError("repository default branch is malformed")
    if not isinstance(html_url, str) or html_url != f"https://github.com/{request.repository}":
        raise ArtifactVerificationError("repository canonical URL is malformed")
    spdx = license_data.get("spdx_id") if isinstance(license_data, dict) else None
    if not isinstance(spdx, str) or spdx in {"NOASSERTION", "Other", ""}:
        raise ArtifactVerificationError("repository has no machine-readable code licence")

    tree_url = _api_url(f"/repos/{request.repository}/git/trees/{quote(branch, safe='')}?recursive=1")
    tree = _json(transport(tree_url))
    entries = tree.get("tree")
    if tree.get("truncated") is True or not isinstance(entries, list):
        raise ArtifactVerificationError("repository tree is incomplete")
    paths = tuple(
        entry.get("path", "").casefold()
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    )
    has_readme = any(path.rsplit("/", 1)[-1].startswith("readme") for path in paths)
    has_test_paths = any(path.startswith(("test/", "tests/")) or "/test_" in path for path in paths)
    has_manifest = any(
        path.rsplit("/", 1)[-1] in {"pyproject.toml", "requirements.txt", "environment.yml", "environment.yaml", "dockerfile", "compose.yaml", "package-lock.json", "poetry.lock"}
        for path in paths
    )
    has_data = any(path.startswith(("data/", "dataset/", "datasets/")) for path in paths)
    evidence = json.dumps(
        {"repository": request.repository, "branch": branch, "licence": spdx, "paths": sorted(paths)},
        separators=(",", ":"),
    ).encode("utf-8")
    return PublicArtifactReceipt(
        source_key=request.source_key,
        claim_id=request.claim_id,
        repository=request.repository,
        api_url=repository_url,
        html_url=html_url,
        default_branch=branch,
        code_license=spdx,
        evidence_sha256=sha256(evidence).hexdigest(),
        has_readme=has_readme,
        has_test_paths=has_test_paths,
        has_environment_manifest=has_manifest,
        has_data_paths=has_data,
    )
