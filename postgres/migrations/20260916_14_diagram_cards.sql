-- Visual research cards only: rendered PNGs and provider file IDs are not retained.
CREATE TABLE IF NOT EXISTS it_research.diagram_cards (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES it_research.documents(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number BETWEEN 1 AND 100),
  card_version TEXT NOT NULL CHECK (card_version = 'diagram-card-v1'),
  analyzer TEXT NOT NULL CHECK (analyzer = 'gigachat-vision'),
  image_sha256 CHAR(64) NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
  card JSONB NOT NULL CHECK (jsonb_typeof(card) = 'object' AND octet_length(card::text) <= 24000),
  card_sha256 CHAR(64) NOT NULL CHECK (card_sha256 ~ '^[0-9a-f]{64}$'),
  reviewer_status TEXT NOT NULL DEFAULT 'needs_review' CHECK (reviewer_status IN ('needs_review','reviewed','rejected')),
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(), reviewed_at TIMESTAMPTZ,
  UNIQUE (document_id, page_number, card_version),
  CHECK ((reviewer_status = 'needs_review' AND reviewed_at IS NULL) OR (reviewer_status IN ('reviewed','rejected') AND reviewed_at IS NOT NULL))
);
