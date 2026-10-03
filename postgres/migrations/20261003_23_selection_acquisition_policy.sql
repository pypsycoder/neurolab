-- Retain legacy receipts/reservations; explicitly permit the new bounded policy.
-- Do not edit already applied migrations or reset acquisition history.
ALTER TABLE it_research.corpus_gap_rounds
    DROP CONSTRAINT corpus_gap_rounds_policy_version_check,
    ADD CONSTRAINT corpus_gap_rounds_policy_version_check
        CHECK (policy_version IN ('corpus-gap-v1','research-selection-v1'));
ALTER TABLE it_research.corpus_fulltext_attempts
    DROP CONSTRAINT corpus_fulltext_attempts_policy_version_check,
    ADD CONSTRAINT corpus_fulltext_attempts_policy_version_check
        CHECK (policy_version IN ('corpus-gap-v1','research-selection-v1'));
