-- Validated experimental artifacts only: never raw prompts/model transcripts.
CREATE TABLE IF NOT EXISTS it_research.experimental_specs (
  run_id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  boundary TEXT NOT NULL CHECK (boundary = 'public_synthetic_experimental_only'),
  packet_sha256 CHAR(64) NOT NULL CHECK (packet_sha256 ~ '^[0-9a-f]{64}$'),
  spec_sha256 CHAR(64) NOT NULL CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),
  model_label TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status = 'draft_experimental'),
  spec JSONB NOT NULL CHECK (jsonb_typeof(spec)='object' AND octet_length(spec::text)<=48000),
  receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object' AND octet_length(receipt::text)<=4096)
);
