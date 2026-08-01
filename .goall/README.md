# `/goall` audit artifacts

This directory contains privacy-conscious attempt records and five-attempt analyses for the current `/goall` run.

- Attempt numbering starts at 001 because no prior `/goall` attempt ledger existed. Existing `.traces` files are pre-run audit inputs, not attempts.
- Raw meal text, API keys, model payloads, tokens, and personal data are not stored here.
- Each attempt points to its local JSONL trace. The trace itself is subject to the repository redaction rules.
- A plan is called `succeeded` only when the required gates and the CLI/trace consistency check are evidenced; offline fixture success remains fixture-scoped.
