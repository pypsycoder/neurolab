-- Publisher HTML frequently changes analytics or presentation markup without
-- changing the visible evidence. Retain one current receipt per semantic text.

DELETE FROM it_research.publisher_html_receipts AS duplicate
USING it_research.publisher_html_receipts AS retained
WHERE duplicate.source_key = retained.source_key
  AND duplicate.visible_text_sha256 = retained.visible_text_sha256
  AND duplicate.id::text > retained.id::text;

ALTER TABLE it_research.publisher_html_receipts
  DROP CONSTRAINT IF EXISTS publisher_html_receipts_source_key_html_sha256_key;

ALTER TABLE it_research.publisher_html_receipts
  ADD CONSTRAINT publisher_html_receipts_source_key_visible_text_sha256_key
  UNIQUE (source_key, visible_text_sha256);
