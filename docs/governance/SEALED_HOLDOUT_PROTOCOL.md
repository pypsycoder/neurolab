# Sealed semantic holdout protocol

The semantic holdout protects prompt and evaluator changes from being optimised
against the small public regression suite. It is not a clinical evaluation and
never receives patient data.

## Boundary

- The held-out prompts, responses, per-case verdicts and judge rationale stay
  in a separate evaluator environment; they are not committed, printed or
  stored in PostgreSQL.
- The project receives one signed aggregate only: opaque case-set hash, count,
  candidate and judge model/artifact hashes, three aggregate metrics and an
  allowlisted judge identifier.
- The verifier rejects a receipt with an invalid HMAC, unknown fields, fewer
  than 20 cases, a different case-set hash, a mismatched candidate identity or
  the same candidate and judge model hash.
- A signed receipt is evidence for the `shadow` evaluator only. It cannot
  promote a prompt, evaluator, code component or clinical workflow by itself.

## Operational separation

The signing key `SEMANTIC_HOLDOUT_RECEIPT_KEY` belongs only in the isolated
evaluator/verifier secret environment. It must not be placed in the Git
repository, ordinary agent environment, runtime receipts or logs. The Code
Agent receives neither the holdout content nor this key.

The verifier command accepts a bounded receipt file and prints only its
aggregate metrics. It persists only after signature verification. A fixture or
locally constructed receipt must never be persisted as external-evaluator
evidence.

## First live run

Before a real run, choose and provision a genuinely distinct judge model and
an isolated evaluator environment. Configure its sealed case set and signing
key there, generate one receipt for the exact candidate artifact/model, and
run the verifier in shadow mode. Promotion remains subject to the existing
comparable-holdout and independent-review gates.
