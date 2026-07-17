# Unified Commerce Workflow — Phase 1A

Phase 1A compiles one complete, immutable review proposal from an existing validated commerce job. It does not publish, change marketplace state, or create an order.

```bash
python scripts/jamesos.py commerce prepare --job-id JOB_ID
python scripts/jamesos.py commerce status --job-id JOB_ID
python scripts/jamesos.py commerce review --job-id JOB_ID
```

`prepare` reuses the ProductOrchestrator listing dry-run, ownership, listing-metadata, visual-review, publication-state, variant, artwork, placement, order, and protected-resource gates. Approved read-only provider queries may occur in normal use. Phase 1A performs no provider writes.

## Proposal and immutable SHA

The canonical proposal binds the job and opaque profile reference, artwork and mockup hashes, listing text, tags, price, colors, sizes, exact variants, placement, destination, expected final state, warnings, and required confirmations. Deterministic UTF-8 JSON with sorted keys produces `proposal_sha256`.

Presentation-only values such as `generated_at`, absolute paths, HTML, and transient timestamps are excluded. Semantically unordered tag, color, size, mockup, warning, and confirmation lists are normalized before hashing. Changing any approval-bound value creates a different SHA and invalidates the prior proposal.

Artifacts are written under the existing private job directory:

```text
commerce-proposal/
  current.json
  current-private.json
  review.html
  proposal-sha256.txt
  archive/<prior-sha>/
```

`current.json` and `review.html` contain safe review fields only. Provider IDs and the private profile binding are isolated in mode-`0600` `current-private.json`. A changed proposal archives and marks its predecessor superseded; only the current proposal is approval-eligible. Identical preparation is idempotent.

The review page is self-contained, escapes listing content, embeds local evidence images, and prominently states **NOT PUBLISHED**, **NO ORDER CREATED**, and **AWAITING FINAL APPROVAL**. Preparing a valid proposal moves only the local job stage to `awaiting_final_approval`; it grants no final approval.

Future phases may add guided revision, exact-SHA approval with publish-once execution, and a Jade review UI. Those phases must preserve the private binding boundary, one-attempt remote writes, final-state verification, and the prohibition on order creation.
