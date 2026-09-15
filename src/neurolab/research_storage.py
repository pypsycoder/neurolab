"""PostgreSQL persistence for the public, non-clinical IT research corpus."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from neurolab.artifact_verification import PublicArtifactReceipt
from neurolab.claim_review import ReviewedClaim
from neurolab.fulltext_verification import FullTextReceipt
from neurolab.it_research import ItResearchRun, ResearchItem
from neurolab.license_verification import LicenseReceipt
from neurolab.publisher_evidence import PublisherHtmlReceipt
from neurolab.research_corpus import CoverageAssessment, SourceAssessment, classify_item


class ItResearchStorageError(RuntimeError):
    """Raised when persistence is unavailable or its public-data contract is broken."""


def _abstract_digest(item: ResearchItem) -> str | None:
    return sha256(item.abstract.encode("utf-8")).hexdigest() if item.abstract else None


def _require_psycopg() -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise ItResearchStorageError("PostgreSQL client is unavailable in this runtime") from error
    return psycopg


def persist_run(database_url: str, run: ItResearchRun, *, artifact_ref: str) -> str:
    """Upsert metadata-only observations, their scores and one bounded run receipt."""
    if not database_url.strip():
        raise ItResearchStorageError("DATABASE_URL is required only when --persist is selected")
    if artifact_ref.startswith(("/", "\\")) or ".." in artifact_ref.split("/"):
        raise ItResearchStorageError("artifact reference must be a relative safe path")
    psycopg = _require_psycopg()
    run_id = str(uuid4())
    topic_digest = sha256(run.query.topic.strip().encode("utf-8")).hexdigest()
    provider_status = json.dumps({"errors": list(run.provider_errors), "audit": list(run.audit)})
    assessments = tuple(classify_item(item) for item in run.items)
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.runs
                        (id, completed_at, pipeline_version, topic_sha256, decision, provider_status, artifact_ref)
                    VALUES (%s, %s, %s, %s, 'collecting_evidence', %s::jsonb, %s)
                    """,
                    (run_id, datetime.now(UTC), "it-research-v0.2", topic_digest, provider_status, artifact_ref),
                )
                for assessment in assessments:
                    _upsert_assessment(cursor, run_id, assessment)
    except Exception as error:  # The caller receives no provider/database details or secrets.
        raise ItResearchStorageError("public research corpus persistence failed") from error
    return run_id


def _upsert_assessment(cursor: Any, run_id: str, assessment: SourceAssessment) -> None:
    item = assessment.item
    cursor.execute(
        """
        INSERT INTO it_research.sources
            (source_key, canonical_doi, canonical_url, title, published_on, last_seen_at, abstract_sha256, verification_status)
        VALUES (%s, %s, %s, %s, %s, now(), %s, %s)
        ON CONFLICT (source_key) DO UPDATE SET
            canonical_doi = COALESCE(EXCLUDED.canonical_doi, it_research.sources.canonical_doi),
            canonical_url = EXCLUDED.canonical_url,
            title = EXCLUDED.title,
            published_on = EXCLUDED.published_on,
            last_seen_at = now(),
            abstract_sha256 = COALESCE(EXCLUDED.abstract_sha256, it_research.sources.abstract_sha256)
        """,
        (
            assessment.source_key,
            item.doi.casefold() if item.doi else None,
            item.url,
            item.title,
            item.published_on,
            _abstract_digest(item),
            assessment.verification_status,
        ),
    )
    cursor.execute(
        """
        INSERT INTO it_research.observations
            (run_id, source_key, provider, provider_id, provider_url, checked_on, evidence_level, limitations, authors)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (run_id, provider, provider_id) DO NOTHING
        """,
        (
            run_id,
            assessment.source_key,
            item.provider,
            item.provider_id,
            item.url,
            item.checked_on,
            item.evidence_level,
            json.dumps(list(item.limitations)),
            json.dumps(list(item.authors)),
        ),
    )
    cursor.execute(
        """
        INSERT INTO it_research.assessments
            (source_key, classifier_version, architecture_layers, classification_confidence,
             conceptual_support, implementation_readiness, reproducibility, source_independence, rationale)
        VALUES (%s, 'metadata-title-v1', %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (source_key) DO UPDATE SET
            assessed_at = now(),
            classifier_version = EXCLUDED.classifier_version,
            architecture_layers = EXCLUDED.architecture_layers,
            classification_confidence = EXCLUDED.classification_confidence,
            conceptual_support = EXCLUDED.conceptual_support,
            implementation_readiness = EXCLUDED.implementation_readiness,
            reproducibility = EXCLUDED.reproducibility,
            source_independence = EXCLUDED.source_independence,
            rationale = EXCLUDED.rationale
        """,
        (
            assessment.source_key,
            list(assessment.architecture_layers),
            assessment.classification_confidence,
            assessment.conceptual_support,
            assessment.implementation_readiness,
            assessment.reproducibility,
            assessment.source_independence,
            json.dumps(list(assessment.rationale)),
        ),
    )


def load_corpus_assessments(database_url: str) -> tuple[SourceAssessment, ...]:
    """Load only the structured public corpus needed by the coverage gate."""
    psycopg = _require_psycopg()
    try:
        with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.source_key, s.canonical_doi, s.canonical_url, s.title,
                           s.published_on::text, s.verification_status,
                           o.provider, o.provider_id, o.checked_on::text, o.evidence_level,
                           o.limitations, o.authors,
                           a.architecture_layers, a.classification_confidence,
                           a.conceptual_support, a.implementation_readiness,
                           a.reproducibility, a.source_independence, a.rationale
                    FROM it_research.sources AS s
                    JOIN it_research.assessments AS a USING (source_key)
                    JOIN it_research.observations AS o USING (source_key)
                    """
                )
                rows = cursor.fetchall()
    except Exception as error:
        raise ItResearchStorageError("public research corpus read failed") from error

    assessments: list[SourceAssessment] = []
    for row in rows:
        item = ResearchItem(
            provider=row["provider"],
            provider_id=row["provider_id"],
            url=row["canonical_url"],
            title=row["title"],
            published_on=row["published_on"],
            checked_on=row["checked_on"],
            evidence_level=row["evidence_level"],
            limitations=tuple(row["limitations"]),
            abstract="",
            authors=tuple(row["authors"]),
            doi=row["canonical_doi"],
        )
        assessments.append(
            SourceAssessment(
                source_key=row["source_key"],
                item=item,
                architecture_layers=tuple(row["architecture_layers"]),
                classification_confidence=float(row["classification_confidence"]),
                conceptual_support=float(row["conceptual_support"]),
                implementation_readiness=float(row["implementation_readiness"]),
                reproducibility=float(row["reproducibility"]),
                source_independence=float(row["source_independence"]),
                verification_status=row["verification_status"],
                rationale=tuple(row["rationale"]),
            )
        )
    return tuple(assessments)


def record_synthesis_status(database_url: str, coverage: CoverageAssessment, *, artifact_ref: str) -> str:
    """Persist the gate receipt, not a speculative LLM task or its prompt."""
    psycopg = _require_psycopg()
    synthesis_id = str(uuid4())
    snapshot = json.dumps(
        {
            "unique_source_count": coverage.unique_source_count,
            "provider_provenance_count": coverage.provider_provenance_count,
            "sources_per_layer": coverage.sources_per_layer,
            "content_verified_count": coverage.content_verified_count,
            "buildable_reproducibility_mean": coverage.buildable_reproducibility_mean,
            "unmet_requirements": list(coverage.unmet_requirements),
        }
    )
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.synthesis_runs
                        (id, coverage_snapshot, decision, artifact_ref, reviewer_status)
                    VALUES (%s, %s::jsonb, %s, %s, 'not_requested')
                    """,
                    (synthesis_id, snapshot, coverage.status, artifact_ref),
                )
    except Exception as error:
        raise ItResearchStorageError("research synthesis receipt persistence failed") from error
    return synthesis_id


def persist_fulltext_receipt(database_url: str, receipt: FullTextReceipt) -> str:
    """Persist only a legal open-access document receipt, never its PDF/text bytes."""
    psycopg = _require_psycopg()
    document_id = str(uuid4())
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.documents
                        (id, source_key, provider, document_url, license_id, pdf_sha256,
                         byte_count, page_count, extracted_text_sha256,
                         extracted_character_count, extraction_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key, pdf_sha256) DO UPDATE SET
                        acquired_at = now(), extraction_status = EXCLUDED.extraction_status
                    RETURNING id
                    """,
                    (
                        document_id,
                        receipt.source_key,
                        receipt.provider,
                        receipt.document_url,
                        receipt.license_id,
                        receipt.sha256,
                        receipt.byte_count,
                        receipt.page_count,
                        receipt.extracted_text_sha256,
                        receipt.extracted_character_count,
                        receipt.extraction_status,
                    ),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise ItResearchStorageError("full-text receipt persistence failed") from error
    return str(row[0])


def persist_license_receipt(database_url: str, receipt: LicenseReceipt) -> str:
    """Persist a licence proof digest, never the untrusted abstract-page HTML."""
    psycopg = _require_psycopg()
    receipt_id = str(uuid4())
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.license_receipts
                        (id, source_key, provider, metadata_url, license_id, evidence_sha256, checked_on)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key, license_id, evidence_sha256) DO UPDATE SET checked_on = EXCLUDED.checked_on
                    RETURNING id
                    """,
                    (
                        receipt_id,
                        receipt.source_key,
                        receipt.provider,
                        receipt.metadata_url,
                        receipt.license_id,
                        receipt.evidence_sha256,
                        receipt.checked_on,
                    ),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise ItResearchStorageError("licence receipt persistence failed") from error
    return str(row[0])


def persist_publisher_html_receipt(database_url: str, receipt: PublisherHtmlReceipt) -> str:
    """Persist a publisher evidence receipt, never its HTML or review excerpt."""
    psycopg = _require_psycopg()
    receipt_id = str(uuid4())
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.publisher_html_receipts
                        (id, source_key, provider, document_url, license_id, html_sha256,
                         visible_text_sha256, visible_character_count, checked_on, verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key, visible_text_sha256) DO UPDATE SET
                        checked_on = EXCLUDED.checked_on,
                        html_sha256 = EXCLUDED.html_sha256
                    RETURNING id
                    """,
                    (
                        receipt_id,
                        receipt.source_key,
                        receipt.provider,
                        receipt.document_url,
                        receipt.license_id,
                        receipt.html_sha256,
                        receipt.visible_text_sha256,
                        receipt.visible_character_count,
                        receipt.checked_on,
                        receipt.verification_status,
                    ),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise ItResearchStorageError("publisher HTML receipt persistence failed") from error
    return str(row[0])


def persist_reviewed_claim(database_url: str, claim: ReviewedClaim) -> str:
    """Write one reviewer-created, page-located claim and its separate score vector."""
    psycopg = _require_psycopg()
    claim_id = str(uuid4())
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT page_count FROM it_research.documents WHERE id = %s AND source_key = %s",
                    (claim.document_id, claim.source_key),
                )
                document = cursor.fetchone()
                if document is None or claim.page_end > document[0]:
                    raise ItResearchStorageError("claim page location is not backed by its document receipt")
                cursor.execute(
                    """
                    INSERT INTO it_research.claims
                        (id, source_key, document_id, claim_summary, evidence_locator, maturity, action_lane, reviewer_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_id, claim_summary) DO UPDATE SET
                        evidence_locator = EXCLUDED.evidence_locator,
                        maturity = EXCLUDED.maturity,
                        action_lane = EXCLUDED.action_lane,
                        reviewer_status = EXCLUDED.reviewer_status
                    RETURNING id
                    """,
                    (
                        claim_id,
                        claim.source_key,
                        claim.document_id,
                        claim.summary,
                        claim.evidence_locator,
                        claim.maturity,
                        claim.action_lane,
                        claim.reviewer_status,
                    ),
                )
                existing = cursor.fetchone()
                cursor.execute(
                    """
                    INSERT INTO it_research.claim_assessments
                        (claim_id, assessor, conceptual_support, empirical_support, reproducibility,
                         feasibility_now, source_independence, uncertainty, rationale)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (claim_id) DO UPDATE SET
                        assessed_at = now(), conceptual_support = EXCLUDED.conceptual_support,
                        empirical_support = EXCLUDED.empirical_support, reproducibility = EXCLUDED.reproducibility,
                        feasibility_now = EXCLUDED.feasibility_now, source_independence = EXCLUDED.source_independence,
                        uncertainty = EXCLUDED.uncertainty, rationale = EXCLUDED.rationale
                    """,
                    (
                        existing[0],
                        claim.assessment.assessor,
                        claim.assessment.conceptual_support,
                        claim.assessment.empirical_support,
                        claim.assessment.reproducibility,
                        claim.assessment.feasibility_now,
                        claim.assessment.source_independence,
                        claim.assessment.uncertainty,
                        json.dumps(list(claim.assessment.rationale)),
                    ),
                )
                if claim.assessment.assessor == "human":
                    cursor.execute(
                        "UPDATE it_research.sources SET verification_status = 'content_verified' WHERE source_key = %s",
                        (claim.source_key,),
                    )
    except ItResearchStorageError:
        raise
    except Exception as error:
        raise ItResearchStorageError("reviewed claim persistence failed") from error
    return str(existing[0])


def persist_public_artifact_receipt(database_url: str, receipt: PublicArtifactReceipt) -> str:
    """Link bounded repository metadata only to a human-reviewed claim."""
    psycopg = _require_psycopg()
    receipt_id = str(uuid4())
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM it_research.claims WHERE id = %s AND source_key = %s AND reviewer_status = 'reviewed'",
                    (receipt.claim_id, receipt.source_key),
                )
                if cursor.fetchone() is None:
                    raise ItResearchStorageError("artifact must be linked to a human-reviewed claim")
                cursor.execute(
                    """
                    INSERT INTO it_research.public_artifact_receipts
                        (id, source_key, claim_id, repository, api_url, html_url, default_branch,
                         code_license, evidence_sha256, has_readme, has_test_paths,
                         has_environment_manifest, has_data_paths, verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id, repository, evidence_sha256) DO UPDATE SET checked_at = now()
                    RETURNING id
                    """,
                    (
                        receipt_id,
                        receipt.source_key,
                        receipt.claim_id,
                        receipt.repository,
                        receipt.api_url,
                        receipt.html_url,
                        receipt.default_branch,
                        receipt.code_license,
                        receipt.evidence_sha256,
                        receipt.has_readme,
                        receipt.has_test_paths,
                        receipt.has_environment_manifest,
                        receipt.has_data_paths,
                        receipt.verification_status,
                    ),
                )
                row = cursor.fetchone()
    except ItResearchStorageError:
        raise
    except Exception as error:
        raise ItResearchStorageError("public artifact receipt persistence failed") from error
    return str(row[0])
