# JamesOS Current Status

_Last updated: July 16, 2026_

JamesOS is a local-first personal operating system and agent platform. The project now includes a working, guarded provider-to-marketplace commerce foundation in addition to its original evidence, memory, Knowledge Graph, Jade, Job Queue, and Creative Studio systems.

## Snapshot

- Test suite at checkpoint: **362 passing tests**
- Runtime data root: `~/JamesOSData/JamesOS`
- Human-authored notes root: `~/Notes`
- Secrets and deployment-specific profiles remain outside Git

## North Star

The preferred commerce experience is:

```text
idea
→ JamesOS generates and validates artwork
→ JamesOS creates or updates a non-public provider draft
→ JamesOS downloads real mockups
→ JamesOS prepares the complete marketplace listing
→ user reviews one immutable listing proposal
→ user approves once
→ JamesOS publishes once
→ JamesOS verifies the listing reached the configured final state
```

Candidate selection, design revisions, contrast fixes, and mockup review are editing steps. They are not final approval.

## Implemented Foundations

### Local assistant platform

- FastAPI backend and Flutter Jade client
- local evidence ingestion and search
- Knowledge Graph and Working Memory
- Reasoner and Planner foundations
- durable Job Queue
- Control Center health and readiness reporting
- phone, email, calendar, and ChatGPT-history ingestion foundations
- local-first storage and evidence grounding

### Agent OS

JamesOS includes a reusable agent runtime with:

- `AgentRegistry`
- `AgentRunner`
- `AgentRequest` and task graph models
- capability-based delegation
- `ToolBroker`
- `SecretProvider`
- `RunLedger`
- `ApprovalPolicy`
- risk levels and explicit approval requirements
- one-attempt remote-write controls
- public-output filtering that avoids secret disclosure

Current commerce agents include:

- `CommerceAgent`
- `PrintifyAgent`
- `EtsyAgent`

Private shops are represented as local `commerce_shop` profiles rather than hard-coded public agents.

## Creative Commerce Capabilities

### Product orchestration

The product orchestrator can:

- parse a product idea into a structured brief
- resolve provider blueprint, provider, colors, sizes, and variants
- generate multiple independent local design candidates
- enforce exact phrase rendering
- validate transparency, dimensions, safe bounds, and candidate uniqueness
- generate human review sheets
- bind human approval to an exact candidate SHA-256
- create a non-public provider draft after explicit confirmation
- recover from failed product creation without duplicating completed side effects
- download exact provider mockups for selected variants
- review placement, artwork IDs, enabled variants, and front-only configuration
- prepare listing metadata
- publish through the provider under explicit confirmation
- resolve the marketplace listing ID
- deactivate a listing for staged-review mode
- verify an active listing for direct-live mode

### Current lower-level CLI

```bash
python scripts/product_from_prompt.py create
python scripts/product_from_prompt.py resume
python scripts/product_from_prompt.py status
python scripts/product_from_prompt.py report
python scripts/product_from_prompt.py reconcile-draft
python scripts/product_from_prompt.py review-design
python scripts/product_from_prompt.py approve-design
python scripts/product_from_prompt.py revise-design-contrast
python scripts/product_from_prompt.py recover-draft
python scripts/product_from_prompt.py update-draft-artwork
python scripts/product_from_prompt.py review-draft
python scripts/product_from_prompt.py prepare-listing
python scripts/product_from_prompt.py send-to-etsy-review
python scripts/product_from_prompt.py deactivate-etsy-listing
python scripts/product_from_prompt.py send-to-etsy-inactive-review
```

Mutating commands default to a dry plan unless their explicit confirmation flag is supplied.

## Approval And Publication Policies

Approval behavior is profile-configurable.

Supported approval modes:

- `single_final`
- `staged`

Supported marketplace final states:

- `active`
- `inactive`

These settings are independent.

A generic private profile can configure:

```json
{
  "approval_mode": "single_final",
  "marketplace_final_state": "active",
  "human_review_location": "jamesos_listing_preview",
  "preapproval_provider_draft_allowed": true,
  "publish_policy": "publish_active_after_approval"
}
```

The final approval is intended to bind to a canonical hash covering:

- selected artwork and exact SHA-256
- provider product and artwork IDs
- product configuration
- enabled variants
- placement
- real mockups
- listing title
- listing description
- marketplace tags
- price
- destination account
- expected final state

Changing any bound field invalidates approval.

Staged publish-and-inactivate behavior remains available for profiles and recovery workflows that require it.

## Provider And Marketplace Status

### Provider integration

Implemented and live-tested:

- shop and catalog reads
- artwork upload
- product draft creation
- exact variant selection
- front-only artwork placement
- draft recovery
- mockup retrieval
- product/listing metadata update
- guarded publication

Remote actions are not automatically retried.

### Marketplace integration

Implemented and live-tested:

- OAuth authorization and refresh handling
- listing reads
- listing-ID resolution following provider publication
- listing deactivation
- inactive-state verification
- active-state verification capability

### Orders

Order creation and fulfillment are not part of the current workflow. JamesOS must never create an order from the product-orchestration path.

## Private Runtime State

Live product jobs, shop names, account identifiers, product identifiers, artwork hashes, protected-resource identifiers, OAuth files, review artifacts, and execution reports belong under `~/JamesOSData/JamesOS` or another private deployment store. They must not be committed to the public repository.

## Safety Invariants

- Secrets never enter Git, proposals, reports, or public agent output.
- Deployment-specific names and identifiers remain outside Git.
- Remote writes require explicit confirmation.
- Publication requires an approval reference appropriate to the profile policy.
- Completed remote side effects are recorded and must not be repeated during recovery.
- No automatic remote retry.
- No automatic republish after an indeterminate publication result.
- No hidden marketplace activation or deactivation.
- No order creation.
- No protected-resource modification.
- Artwork changes invalidate exact-hash approval.
- Final proposal changes invalidate final approval.

## Remaining Major Milestone

The main missing user-facing feature is a unified commerce command that chains the existing lower-level components into the preferred flow:

```text
jamesos commerce create --profile PRIVATE_PROFILE_ID --idea "..."
→ review and revise one complete listing package
jamesos commerce approve --job-id ... --proposal-sha256 ... --confirm
→ publish once and verify the configured marketplace final state
```

The implementation should add:

- a complete immutable `CommerceProposal`
- canonical proposal hashing
- a listing-review HTML page with real mockups
- profile-selected approval behavior
- a durable execution state machine
- idempotent recovery that never repeats completed remote writes
- an execution report showing every attempted and completed side effect

Existing lower-level commands should remain available for diagnostics and expert recovery.

## Resume On Another Machine

Code:

```bash
cd ~/JamesOS
git pull --ff-only origin master
python -m unittest discover tests
```

Runtime state, private profiles, artwork, OAuth files, and reports live outside Git and must be synchronized securely before continuing on another machine.
