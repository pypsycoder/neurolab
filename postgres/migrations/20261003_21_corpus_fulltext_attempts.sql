CREATE TABLE IF NOT EXISTS it_research.corpus_fulltext_attempts (
    run_id UUID PRIMARY KEY,
    policy_version TEXT NOT NULL CHECK (policy_version = 'corpus-gap-v1'),
    source_key TEXT NOT NULL REFERENCES it_research.sources(source_key),
    status TEXT NOT NULL CHECK (status IN
        ('inflight','completed','license_unverified','document_unverified')),
    receipt JSONB NOT NULL CHECK (octet_length(receipt::text) <= 24000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (policy_version,source_key),
    CHECK ((status = 'inflight') = (completed_at IS NULL))
);
