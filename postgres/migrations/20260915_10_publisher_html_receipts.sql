-- Bounded, open-licence publisher HTML evidence.  Raw HTML and excerpts are
-- intentionally excluded: the database stores only reviewable receipts.

CREATE TABLE IF NOT EXISTS it_research.publisher_html_receipts (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider = 'f1000research'),
  document_url TEXT NOT NULL CHECK (document_url ~ '^https://f1000research\.com/articles/[0-9]{1,3}-[0-9]{1,6}/v[0-9]{1,2}$'),
  license_id TEXT NOT NULL CHECK (license_id = 'CC-BY-4.0'),
  html_sha256 CHAR(64) NOT NULL,
  visible_text_sha256 CHAR(64) NOT NULL,
  visible_character_count INTEGER NOT NULL CHECK (visible_character_count > 0),
  checked_on DATE NOT NULL,
  verification_status TEXT NOT NULL CHECK (verification_status = 'publisher_html_verified'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_key, html_sha256)
);

CREATE INDEX IF NOT EXISTS it_research_publisher_html_receipts_source_idx
  ON it_research.publisher_html_receipts(source_key, checked_on DESC);
