# Agent capability reuse

JamesOS keeps business workflows in agents and shares only infrastructure and provider boundaries.

```text
Agent (Scout / Producer / Commerce)
  -> Agent OS capability contract
     -> provider adapter (deterministic, local model, creative studio, commerce)
  -> shared persistence / approval / audit layer
```

## Focused audit

Existing shared implementations retained:

- `product_orchestrator._atomic_json` remains the established Commerce writer and is already reused by Agency shell state, mockup review, and mockup composition. Moving mature Commerce journals is deliberately out of scope.
- `RunLedger` remains the sanitized Agent OS run ledger used by Book Opportunity Scout.
- Commerce publication and preparation journals remain authoritative for uncertain provider writes and idempotent publication.
- Commerce proposal hashes and profile approval guards remain domain-specific because they bind destinations, variants, artwork, and provider state.

Duplication removed:

- Scout and Coloring Book Producer independently implemented temporary-file JSON/text replacement.
- Producer independently implemented canonical JSON hashing, JSONL audit events, revision-bound approval hashes, and stale-approval detection.
- Mockup composition declared its own future blank-model provider protocol.

The shared `jamesos.core.artifacts` module now provides `AtomicDocumentStore`, `ProjectArtifactStore`, `VersionedDocument`, `ApprovalService`, `OperationJournal`, `AuditEventStore`, canonical/file SHA-256 helpers, and a provider-free safety declaration. These are low-level Agent OS services, not Agency agents. Existing filenames and JSON structures remain unchanged.

## Intentionally agent-specific

- Book Opportunity Scout owns research collection, evidence confidence, ranking, and candidate decisions.
- Coloring Book Producer owns approved-candidate validation, book configuration, revision transitions, and local brief approval.
- Commerce owns shop/destination binding, artwork and variant integrity, provider journals, publication uncertainty, and no-order enforcement.
- Mockup review owns Printify mockup intake; deterministic composition owns mask, perspective, and template quality checks.
- Agency owns install/enable/remove lifecycle and permission review.

## Planning and creative capabilities

`StructuredPlanProvider` returns structured candidates without owning project state. `DeterministicPlanProvider` is the provider-free implementation for tests and future Page Plan work. `OllamaPlanProvider` is only a future protocol; this refactor never contacts Ollama.

`LocalCreativeStudioProvider` accepts a `LocalAssetRequest` and returns a `LocalAssetResult`. Coloring Book Producer, Commerce, mockups, and cover workflows may compose this capability. `BlankModelTemplateProvider` is the single future blank-template boundary, so agents must not add direct ComfyUI clients. No ComfyUI implementation is installed here.

## Compatibility

The shared services read and write the existing Scout run and Producer project formats. Producer approval hashing deliberately retains the existing `{book_brief, production_spec, revision}` canonical payload, so prior approvals do not become stale merely because of this refactor. No migration or directory rewrite is required.
