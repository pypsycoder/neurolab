"""Append-only redacted selection receipts; no abstracts, source text or prompts."""
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row

from neurolab.research_selection import VERSION, SelectionReceipt, metadata_matches, digest


def persist_selection(database_url: str, receipt: SelectionReceipt) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("""INSERT INTO it_research.selection_receipts
            (id,source_key,policy_version,stage,mission_id,input_sha256,decision,receipt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (policy_version,stage,mission_id,source_key,input_sha256) DO NOTHING""",
            (uuid4(), receipt.source_key, VERSION, receipt.stage, receipt.mission_id,
             receipt.input_sha256, receipt.decision, receipt.model_dump_json()))


def load_metadata_selections(database_url: str) -> tuple[SelectionReceipt, ...]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute("""SELECT r.receipt,s.source_key,s.title,s.abstract_sha256
            FROM it_research.selection_receipts r JOIN it_research.sources s USING (source_key)
            WHERE r.policy_version=%s AND r.stage='metadata'
            ORDER BY r.created_at DESC,r.id DESC""", (VERSION,)).fetchall()
    selected, seen = [], set()
    for row in rows:
        receipt = SelectionReceipt.model_validate(row["receipt"])
        identity = (receipt.source_key, receipt.mission_id)
        # Latest verdict is authoritative, including hold/reject. Do not fall
        # back to a past positive when a new assessment denies admission.
        if identity in seen:
            continue
        seen.add(identity)
        if metadata_matches(receipt, source_key=row["source_key"], title=row["title"], abstract_sha256=row["abstract_sha256"]):
            selected.append(receipt)
    return tuple(selected)


def require_metadata_selection(database_url: str, source_key: str) -> tuple[SelectionReceipt, ...]:
    selected = tuple(r for r in load_metadata_selections(database_url) if r.source_key == source_key)
    if not selected:
        raise ValueError("metadata task relevance gate closed; rescreen source before PDF analysis")
    return selected


def eligible_content_cards(database_url: str, *, mission_id: str) -> frozenset[tuple[str, str, str]]:
    return frozenset(admitted_content_pages(database_url, mission_id=mission_id))


def admitted_content_pages(database_url: str, *, mission_id: str) -> dict[tuple[str, str, str], tuple[tuple[int, int], ...]]:
    metadata = {(r.source_key, r.mission_id): r for r in load_metadata_selections(database_url)}
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute("""SELECT receipt FROM it_research.selection_receipts
            WHERE policy_version=%s AND stage='content' AND mission_id=%s
            ORDER BY created_at DESC,id DESC""", (VERSION, mission_id)).fetchall()
    eligible, seen = {}, set()
    for row in rows:
        r = SelectionReceipt.model_validate(row["receipt"])
        key = (r.source_key, r.document_sha256, r.card_sha256)
        if key in seen:
            continue
        seen.add(key)
        m = metadata.get((r.source_key, r.mission_id))
        if (m and r.stage == "content" and r.mission_id == mission_id and r.mission_sha256 == m.mission_sha256
                and r.decision in {"useful_experimental", "explore"} and r.finding_pages
                and r.input_sha256 == digest({"card": r.card_sha256, "pdf": r.document_sha256, "metadata": digest(m)})):
            eligible[key] = tuple(r.finding_pages)
    return eligible
