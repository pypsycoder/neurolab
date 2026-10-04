-- Карточки под задачу сохраняются отдельно от прежних общих пересказов.
CREATE TABLE it_research.task_document_cards (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE RESTRICT,
    document_id UUID NOT NULL REFERENCES it_research.documents(id) ON DELETE RESTRICT,
    policy_version TEXT NOT NULL CHECK (policy_version = 'task-document-v1'),
    mission_id TEXT NOT NULL CHECK (mission_id IN ('architecture','workflow','evaluation','provenance','contracts','theory')),
    mission_sha256 CHAR(64) NOT NULL CHECK (mission_sha256 ~ '^[0-9a-f]{64}$'),
    metadata_sha256 CHAR(64) NOT NULL CHECK (metadata_sha256 ~ '^[0-9a-f]{64}$'),
    model_label TEXT NOT NULL CHECK (length(model_label) BETWEEN 1 AND 100),
    pdf_sha256 CHAR(64) NOT NULL CHECK (pdf_sha256 ~ '^[0-9a-f]{64}$'),
    card_sha256 CHAR(64) NOT NULL CHECK (card_sha256 ~ '^[0-9a-f]{64}$'),
    card JSONB NOT NULL CHECK (jsonb_typeof(card) = 'object' AND octet_length(card::text) <= 48000),
    audit JSONB NOT NULL CHECK (jsonb_typeof(audit) = 'object' AND octet_length(audit::text) <= 60000),
    reviewer_status TEXT NOT NULL DEFAULT 'needs_review' CHECK (reviewer_status = 'needs_review'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, mission_sha256, metadata_sha256, policy_version, model_label, card_sha256)
);

CREATE FUNCTION it_research.reject_task_card_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'task_document_cards are append-only';
END;
$$;
CREATE TRIGGER task_document_cards_append_only
BEFORE UPDATE OR DELETE ON it_research.task_document_cards
FOR EACH ROW EXECUTE FUNCTION it_research.reject_task_card_mutation();
