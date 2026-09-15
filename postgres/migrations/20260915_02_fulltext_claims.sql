-- Open-access document receipts and reviewer-created claims.  PDF bytes and
-- extracted raw text are intentionally excluded: they remain ephemeral,
-- untrusted runtime data subject to a future retention decision.

CREATE TABLE IF NOT EXISTS it_research.documents (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider = 'arxiv'),
  document_url TEXT NOT NULL CHECK (document_url ~ '^https://(arxiv\.org|export\.arxiv\.org)/pdf/'),
  license_id TEXT NOT NULL CHECK (license_id IN ('CC-BY-4.0', 'CC0-1.0', 'PUBLIC-DOMAIN')),
  pdf_sha256 CHAR(64) NOT NULL,
  byte_count INTEGER NOT NULL CHECK (byte_count > 0 AND byte_count <= 26214400),
  page_count INTEGER NOT NULL CHECK (page_count >= 0 AND page_count <= 100),
  extracted_text_sha256 CHAR(64) NOT NULL,
  extracted_character_count INTEGER NOT NULL CHECK (extracted_character_count >= 0 AND extracted_character_count <= 1000000),
  extraction_status TEXT NOT NULL CHECK (extraction_status = 'extracted_untrusted'),
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_key, pdf_sha256)
);

CREATE TABLE IF NOT EXISTS it_research.claims (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES it_research.documents(id) ON DELETE RESTRICT,
  claim_summary TEXT NOT NULL CHECK (char_length(claim_summary) BETWEEN 20 AND 1200 AND claim_summary !~ '[\r\n]'),
  evidence_locator TEXT NOT NULL CHECK (evidence_locator ~ '^pages? [0-9]+(-[0-9]+)?$'),
  maturity TEXT NOT NULL CHECK (maturity IN ('hypothesis', 'formal_or_method', 'simulated_or_benchmarked', 'prototype', 'replicated', 'operational')),
  action_lane TEXT NOT NULL CHECK (action_lane IN ('watchlist', 'research_experiment', 'implementation_candidate', 'production_candidate')),
  reviewer_status TEXT NOT NULL DEFAULT 'needs_review' CHECK (reviewer_status IN ('needs_review', 'reviewed', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, claim_summary)
);

CREATE TABLE IF NOT EXISTS it_research.claim_assessments (
  claim_id UUID PRIMARY KEY REFERENCES it_research.claims(id) ON DELETE CASCADE,
  assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  assessor TEXT NOT NULL CHECK (assessor IN ('human', 'deterministic', 'approved_model')),
  conceptual_support NUMERIC(4,3) CHECK (conceptual_support BETWEEN 0 AND 1),
  empirical_support NUMERIC(4,3) CHECK (empirical_support BETWEEN 0 AND 1),
  reproducibility NUMERIC(4,3) CHECK (reproducibility BETWEEN 0 AND 1),
  feasibility_now NUMERIC(4,3) CHECK (feasibility_now BETWEEN 0 AND 1),
  source_independence NUMERIC(4,3) CHECK (source_independence BETWEEN 0 AND 1),
  uncertainty TEXT NOT NULL CHECK (uncertainty IN ('low', 'medium', 'high', 'unknown')),
  rationale JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS it_research.iteration_outcomes (
  id UUID PRIMARY KEY,
  claim_id UUID REFERENCES it_research.claims(id) ON DELETE SET NULL,
  implementation_ref TEXT NOT NULL CHECK (implementation_ref !~ '(^/|\\|\.\.)'),
  outcome TEXT NOT NULL CHECK (outcome IN ('adopted', 'revised', 'component_saved', 'discarded')),
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  reviewer_status TEXT NOT NULL DEFAULT 'review_required' CHECK (reviewer_status IN ('review_required', 'approved', 'rejected')),
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS it_research_documents_source_idx ON it_research.documents(source_key);
CREATE INDEX IF NOT EXISTS it_research_claims_source_idx ON it_research.claims(source_key);
CREATE INDEX IF NOT EXISTS it_research_claims_lane_idx ON it_research.claims(action_lane, reviewer_status);
