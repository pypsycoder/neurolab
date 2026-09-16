-- Permit the already bounded F1000 CC-BY document receipt alongside arXiv.
-- The PDF/text bytes remain out of PostgreSQL.

ALTER TABLE it_research.documents
  DROP CONSTRAINT IF EXISTS documents_provider_check;

ALTER TABLE it_research.documents
  ADD CONSTRAINT documents_provider_check
  CHECK (provider IN ('arxiv', 'f1000research'));

ALTER TABLE it_research.documents
  DROP CONSTRAINT IF EXISTS documents_document_url_check;

ALTER TABLE it_research.documents
  ADD CONSTRAINT documents_document_url_check
  CHECK (
    document_url ~ '^https://(arxiv\.org|export\.arxiv\.org)/pdf/'
    OR document_url ~ '^https://f1000research-files\.f1000\.com/manuscripts/[0-9]+/[0-9a-f-]+_f1000res[0-9]+\.pdf$'
  );
