"""Сохранение карточек под задачу без обновления исторических результатов."""
import json
from uuid import UUID, uuid4
import psycopg
from psycopg.rows import dict_row

from neurolab.document_cards import DocumentCardError, parse_document_card
from neurolab.document_analysis_assessment import assess_document_analysis
from neurolab.research_selection import digest
from neurolab.task_document_cards import VERSION, require_task_selection, validate_task_card, task_context


def persist_task_card(database_url, card, selection, audit):
    validate_task_card(card)
    context = task_context(selection.mission_id)
    if (audit.get("task_context") != context or audit.get("card_sha256") != card.card_sha256
            or audit.get("source_key") != card.source_key or audit.get("document_id") != card.document_id
            or audit.get("status") != "needs_review" or audit.get("analysis_mode") != "task_conditioned_shadow"
            or audit.get("document_sha256") != card.document_sha256):
        raise DocumentCardError("task card audit mismatch")
    UUID(audit["run_id"])
    if not isinstance(audit.get("model_label"), str) or not 1 <= len(audit["model_label"]) <= 100:
        raise DocumentCardError("task model identity missing")
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = conn.execute("""SELECT d.pdf_sha256,d.page_count,s.title,s.abstract_sha256
            FROM it_research.documents d JOIN it_research.sources s USING(source_key)
            WHERE d.id=%s AND d.source_key=%s""", (card.document_id, card.source_key)).fetchone()
        if row is None or row["pdf_sha256"] != card.document_sha256:
            raise DocumentCardError("task card exact document missing")
        if selection.abstract_sha256 != row["abstract_sha256"]:
            raise DocumentCardError("task card metadata changed")
        require_task_selection((selection,), mission_id=selection.mission_id,
                               source_key=card.source_key, title=row["title"])
        if any(f.page_end > row["page_count"] for f in card.findings):
            raise DocumentCardError("task finding outside persisted document")
        if not assess_document_analysis(card, audit, page_count=row["page_count"],
                                       pdf_sha256=row["pdf_sha256"])["structure_passed"]:
            raise DocumentCardError("task analysis receipt incomplete")
        args = (uuid4(), audit["run_id"], card.source_key, card.document_id, VERSION,
                selection.mission_id, context["mission_sha256"], digest(selection), audit["model_label"],
                card.document_sha256, card.card_sha256, card.as_json(), json.dumps(audit))
        inserted = conn.execute("""INSERT INTO it_research.task_document_cards
            (id,run_id,source_key,document_id,policy_version,mission_id,mission_sha256,metadata_sha256,
             model_label,pdf_sha256,card_sha256,card,audit)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT (document_id,mission_sha256,metadata_sha256,policy_version,model_label,card_sha256)
            DO NOTHING RETURNING id::text""", args).fetchone()
        if inserted:
            return inserted["id"]
        return conn.execute("""SELECT id::text FROM it_research.task_document_cards WHERE
            document_id=%s AND mission_sha256=%s AND metadata_sha256=%s AND policy_version=%s
            AND model_label=%s AND card_sha256=%s""", (card.document_id, context["mission_sha256"],
            digest(selection), VERSION, audit["model_label"], card.card_sha256)).fetchone()["id"]


def load_task_card(database_url, card_id):
    UUID(str(card_id))
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = conn.execute("""SELECT t.*,t.document_id::text AS document_identity,
            d.page_count,d.document_url,d.license_id FROM it_research.task_document_cards t
            JOIN it_research.documents d ON d.id=t.document_id AND d.source_key=t.source_key
            AND d.pdf_sha256=t.pdf_sha256 WHERE t.id=%s""", (card_id,)).fetchone()
    if row is None:
        raise DocumentCardError("task card missing")
    value = dict(row["card"])
    for key in ("source_key", "document_id", "document_sha256", "reviewer_status", "card_version"):
        value.pop(key, None)
    card = parse_document_card(json.dumps(value), source_key=row["source_key"],
        document_id=row["document_identity"], document_sha256=row["pdf_sha256"], page_count=row["page_count"])
    validate_task_card(card)
    if card.card_sha256 != row["card_sha256"]:
        raise DocumentCardError("task card digest mismatch")
    return card, row
