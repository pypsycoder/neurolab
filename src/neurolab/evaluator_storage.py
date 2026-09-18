"""PostgreSQL receipts for evaluator evolution and solution-memory transitions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from uuid import uuid4

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun, EvaluatorDecision, EvaluatorEvolutionError, EvaluatorVersion
from neurolab.solution_memory import SolutionAsset, SolutionMemoryError, SolutionOutcome, next_asset_state


class EvaluatorStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluatorReceipt:
    """Latest redacted result for one exact evaluator definition."""

    kind: str
    version: str
    state: str
    definition_sha256: str
    metrics: EvaluationMetrics | None


def _psycopg() -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise EvaluatorStorageError("PostgreSQL client is unavailable") from error
    return psycopg


def _url(database_url: str) -> None:
    if not database_url.strip():
        raise EvaluatorStorageError("DATABASE_URL is required")


def persist_evaluator_version(database_url: str, evaluator: EvaluatorVersion) -> str:
    """Idempotently write one definition, never test content or prompts.

    A repeated shadow run may reuse an immutable version only when every
    identity-bearing field is identical.  A label collision cannot silently
    overwrite a previously registered evaluator.
    """
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.evaluator_versions
                    (id, evaluator_kind, version_label, parent_id, definition_sha256,
                     frozen_case_set_sha256, active_case_set_sha256, state, proposed_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (evaluator_kind, version_label) DO NOTHING
                    RETURNING id, parent_id, definition_sha256,
                              frozen_case_set_sha256, active_case_set_sha256,
                              state, proposed_by
                    """,
                    (evaluator.evaluator_id, evaluator.kind, evaluator.version, evaluator.parent_evaluator_id,
                     evaluator.definition_sha256, evaluator.frozen_case_set_sha256,
                     evaluator.active_case_set_sha256, evaluator.state, evaluator.proposed_by),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        SELECT id, parent_id, definition_sha256,
                               frozen_case_set_sha256, active_case_set_sha256,
                               state, proposed_by
                        FROM it_research.evaluator_versions
                        WHERE evaluator_kind = %s AND version_label = %s
                        """,
                        (evaluator.kind, evaluator.version),
                    )
                    row = cursor.fetchone()
    except Exception as error:
        raise EvaluatorStorageError("evaluator version persistence failed") from error
    expected = (
        evaluator.parent_evaluator_id,
        evaluator.definition_sha256,
        evaluator.frozen_case_set_sha256,
        evaluator.active_case_set_sha256,
        evaluator.state,
        evaluator.proposed_by,
    )
    if row is None:
        raise EvaluatorStorageError("evaluator version label already exists")
    if tuple(str(value) if value is not None else None for value in row[1:]) != expected:
        raise EvaluatorStorageError("evaluator version label conflicts with an immutable definition")
    return str(row[0])


def persist_evaluation_run(database_url: str, run: EvaluationRun) -> str:
    """Write one redacted holdout result attached to an existing evaluator."""
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.evaluator_runs
                    (id, evaluator_id, cohort_sha256, assessor, assessor_role, metrics, evaluated_case_count)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id
                    """,
                    (run.run_id, run.evaluator_id, run.cohort_sha256, run.assessor, run.assessor_role,
                     run.metrics.as_json(), run.metrics.evaluated_case_count),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise EvaluatorStorageError("evaluation run persistence failed") from error
    return str(row[0])


def load_evaluator_receipt(database_url: str, *, kind: str, version: str) -> EvaluatorReceipt | None:
    """Load an exact evaluator's latest aggregate receipt, never case content."""
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT evaluator_kind, version_label, state, definition_sha256,
                           latest.metrics, latest.evaluated_case_count
                    FROM it_research.evaluator_versions
                    LEFT JOIN LATERAL (
                        SELECT metrics, evaluated_case_count
                        FROM it_research.evaluator_runs
                        WHERE evaluator_id = evaluator_versions.id
                        ORDER BY completed_at DESC, id DESC
                        LIMIT 1
                    ) AS latest ON TRUE
                    WHERE evaluator_kind = %s AND version_label = %s
                    """,
                    (kind, version),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise EvaluatorStorageError("evaluator receipt read failed") from error
    if row is None:
        return None
    raw_metrics = row["metrics"]
    if raw_metrics is None:
        metrics = None
    else:
        if not isinstance(raw_metrics, dict):
            raise EvaluatorStorageError("stored evaluator metrics are malformed")
        try:
            metrics = EvaluationMetrics(
                primary_quality=float(raw_metrics["primary_quality"]),
                safety_quality=float(raw_metrics["safety_quality"]),
                calibration_quality=float(raw_metrics["calibration_quality"]),
                cost_efficiency=float(raw_metrics["cost_efficiency"]),
                evaluated_case_count=int(row["evaluated_case_count"]),
            )
        except (KeyError, TypeError, ValueError, EvaluatorEvolutionError) as error:
            raise EvaluatorStorageError("stored evaluator metrics are malformed") from error
    return EvaluatorReceipt(
        kind=str(row["evaluator_kind"]),
        version=str(row["version_label"]),
        state=str(row["state"]),
        definition_sha256=str(row["definition_sha256"]),
        metrics=metrics,
    )


def persist_evaluator_decision(database_url: str, decision: EvaluatorDecision) -> str:
    """Atomically record a decision and transition only its candidate evaluator."""
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT evaluator_id FROM it_research.evaluator_runs
                    WHERE id IN (%s, %s) ORDER BY id
                    """,
                    (decision.baseline_run_id, decision.candidate_run_id),
                )
                run_evaluators = {str(row[0]) for row in cursor.fetchall()}
                if run_evaluators != {decision.baseline_evaluator_id, decision.candidate_evaluator_id}:
                    raise EvaluatorStorageError("decision runs do not match evaluator identities")
                cursor.execute(
                    """
                    UPDATE it_research.evaluator_versions SET state = %s
                    WHERE id = %s AND state IN ('proposed','shadow')
                    RETURNING id
                    """,
                    (decision.decision, decision.candidate_evaluator_id),
                )
                if cursor.fetchone() is None:
                    raise EvaluatorStorageError("candidate evaluator is not eligible for a state transition")
                cursor.execute(
                    """
                    INSERT INTO it_research.evaluator_decisions
                    (id, baseline_evaluator_id, candidate_evaluator_id, baseline_run_id,
                     candidate_run_id, decision, reason_codes, policy_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id
                    """,
                    (decision.decision_id, decision.baseline_evaluator_id, decision.candidate_evaluator_id,
                     decision.baseline_run_id, decision.candidate_run_id, decision.decision,
                     json.dumps(list(decision.reason_codes)), decision.policy_version),
                )
                row = cursor.fetchone()
    except EvaluatorStorageError:
        raise
    except Exception as error:
        raise EvaluatorStorageError("evaluator decision persistence failed") from error
    return str(row[0])


def persist_solution_asset(database_url: str, asset: SolutionAsset) -> str:
    """Idempotently register an immutable asset receipt without resetting state."""
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO it_research.solution_assets (id, asset_kind, label, content_sha256, state)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (asset_kind, content_sha256) DO NOTHING
                    RETURNING id, label
                    """,
                    (asset.asset_id, asset.kind, asset.label, asset.content_sha256, asset.state),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        SELECT id, label FROM it_research.solution_assets
                        WHERE asset_kind = %s AND content_sha256 = %s
                        """,
                        (asset.kind, asset.content_sha256),
                    )
                    row = cursor.fetchone()
    except Exception as error:
        raise EvaluatorStorageError("solution asset persistence failed") from error
    if row is None or str(row[1]) != asset.label:
        raise EvaluatorStorageError("solution asset conflicts with an immutable receipt")
    return str(row[0])


def persist_solution_outcomes(database_url: str, asset: SolutionAsset, outcomes: tuple[SolutionOutcome, ...]) -> str:
    """Store outcomes and derive state from the complete persisted history."""
    _url(database_url); psycopg = _psycopg()
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                for outcome in outcomes:
                    cursor.execute(
                        """
                        INSERT INTO it_research.solution_outcomes
                        (id, asset_id, synthetic_run_sha256, evaluator_run_id, outcome, primary_quality, safety_quality)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (asset_id, synthetic_run_sha256, evaluator_run_id) DO NOTHING
                        """,
                        (str(uuid4()), outcome.asset_id, outcome.synthetic_run_sha256, outcome.evaluator_run_id,
                         outcome.outcome, outcome.primary_quality, outcome.safety_quality),
                    )
                cursor.execute(
                    """
                    SELECT synthetic_run_sha256, evaluator_run_id, outcome, primary_quality, safety_quality
                    FROM it_research.solution_outcomes WHERE asset_id = %s
                    ORDER BY recorded_at, id
                    """,
                    (asset.asset_id,),
                )
                history = tuple(
                    SolutionOutcome(asset.asset_id, str(row[0]), str(row[1]), str(row[2]), float(row[3]), float(row[4]))
                    for row in cursor.fetchall()
                )
                next_state = next_asset_state(asset, history)
                cursor.execute(
                    "UPDATE it_research.solution_assets SET state = %s WHERE id = %s RETURNING id",
                    (next_state, asset.asset_id),
                )
                row = cursor.fetchone()
    except Exception as error:
        raise EvaluatorStorageError("solution outcome persistence failed") from error
    if row is None:
        raise EvaluatorStorageError("solution asset does not exist")
    return str(row[0])
