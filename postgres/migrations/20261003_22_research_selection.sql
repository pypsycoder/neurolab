CREATE TABLE IF NOT EXISTS it_research.selection_receipts (
    id UUID PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES it_research.sources(source_key),
    policy_version TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('metadata','content')),
    mission_id TEXT NOT NULL,
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    decision TEXT NOT NULL CHECK (decision IN ('admit','explore','hold','reject','useful_experimental','insufficient')),
    receipt JSONB NOT NULL CHECK (octet_length(receipt::text) <= 16384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (policy_version,stage,mission_id,source_key,input_sha256)
);
