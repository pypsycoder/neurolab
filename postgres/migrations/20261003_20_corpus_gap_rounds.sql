-- Public metadata acquisition only; separate from paid/model budget accounting.
CREATE TABLE IF NOT EXISTS it_research.corpus_gap_rounds (
    run_id UUID PRIMARY KEY,
    policy_version TEXT NOT NULL CHECK (policy_version = 'corpus-gap-v1'),
    template_id TEXT NOT NULL CHECK (template_id IN
        ('architecture','workflow','evaluation','provenance','contracts','theory')),
    status TEXT NOT NULL CHECK (status IN ('inflight','completed','unavailable')),
    receipt JSONB NOT NULL CHECK (octet_length(receipt::text) <= 24000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (policy_version, template_id),
    CHECK ((status = 'inflight') = (completed_at IS NULL))
);
