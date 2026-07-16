# JamesOS Current Status

_Last updated: July 16, 2026_

JamesOS is a local-first personal operating system and agent platform. The project now includes a working, guarded Printify-to-Etsy commerce foundation in addition to its original evidence, memory, Knowledge Graph, Jade, Job Queue, and Creative Studio systems.

## Snapshot

- Main branch checkpoint: `e37313c`
- Test suite at checkpoint: **362 passing tests**
- Repository state at checkpoint: clean and pushed to `origin/master`
- Runtime data root: `~/JamesOSData/JamesOS`
- Human-authored notes root: `~/Notes`
- Secrets remain outside Git under `~/JamesOSData/JamesOS/Secrets`

## North Star

The preferred UnityStitches experience is:

```text
idea
→ JamesOS generates and validates artwork
→ JamesOS creates or updates a non-public Printify draft
→ JamesOS downloads real mockups
→ JamesOS prepares the complete Etsy listing
→ James reviews one immutable listing proposal
→ James approves once
→ JamesOS publishes once
→ JamesOS verifies the Etsy listing is active
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

JamesOS now includes a reusable agent runtime with:

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

UnityStitches is represented as a generic `commerce_shop` profile rather than a hard-coded agent.

## Creative Commerce Capabilities

### Product orchestration

The product orchestrator can:

- parse a product idea into a structured brief
- resolve Printify blueprint, provider, colors, sizes, and variants
- generate multiple independent local design candidates
- enforce exact phrase rendering
- validate transparency, dimensions, safe bounds, and candidate uniqueness
- generate human review sheets
- bind human approval to an exact candidate SHA-256
- create a Printify draft after explicit confirmation
- recover from a failed product-create attempt without duplicating completed side effects
- download exact Printify mockups for selected variants
- review placement, artwork IDs, enabled variants, and front-only configuration
- prepare listing metadata
- publish through Printify under explicit confirmation
- resolve an Etsy listing ID
- deactivate an Etsy listing for staged-review mode
- verify an Etsy listing is active for direct-live mode

### Current lower-level CLI

The current diagnostic and expert workflow is exposed through:

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

Supported Etsy final states:

- `active`
- `inactive`

These settings are independent.

### UnityStitches policy

UnityStitches currently uses:

```json
{
  "approval_mode": "single_final",
  "etsy_final_state": "active",
  "human_review_location": "jamesos_listing_preview",
  "preapproval_printify_draft_allowed": true,
  "publish_policy": "publish_active_after_approval"
}
```

The final approval is intended to bind to a canonical hash covering:

- selected artwork and exact SHA-256
- Printify product and artwork IDs
- product configuration
- enabled variants
- placement
- real mockups
- Etsy title
- Etsy description
- Etsy tags
- price
- destination shop
- expected final Etsy state

Changing any bound field invalidates approval.

Staged publish-and-inactivate behavior remains available for other profiles and recovery workflows.

## Printify And Etsy Status

### Printify

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

### Etsy

Implemented and live-tested:

- OAuth authorization and refresh handling
- listing reads
- listing-ID resolution following Printify publication
- listing deactivation
- inactive-state verification
- active-state verification capability

The normal UnityStitches target is now `active` after one final approval. Deactivation remains available for staged mode, emergency handling, and recovery.

### Orders

Order creation and fulfillment are not part of the current workflow. JamesOS must never create an order from the product-orchestration path.

## Current Product Checkpoint

Current job:

```text
product-20260716-143241-e28be82c
```

Current Printify draft:

```text
6a593931a0497a61da04aca4
```

Current state:

- Printify product exists as a non-published draft
- 18 enabled variants
- Black, Dark Grey Heather, and White
- sizes S through 3XL
- front artwork only
- placement: `x=0.5`, `y=0.46`, `scale=0.85`, `angle=0`
- no Etsy listing has been created for this job
- no order has been created

The first approved artwork displayed poorly on White garments. A revised universal-contrast candidate has been generated locally:

```text
candidate: prompt_centered_universal_contrast
sha256: b98ed53099a622195d1c8b9ad244bf119ce75b3d044a35614207f2fe9ffed4df
```

Treatment:

- dark navy fill
- white inner outline
- dark outer stroke
- exact phrase: `YOU ARE SAFE WITH ME`

Automated contrast checks pass against Black, Dark Grey Heather, and White. Human visual review is still required. The revised artwork has not yet been uploaded to Printify, and the existing Printify draft has not yet been updated with it.

Next read-only command:

```bash
python scripts/product_from_prompt.py review-design \
  --job-id product-20260716-143241-e28be82c
```

## Protected Resources

The protected Printify baseline product must never be modified:

```text
6a57eaa752f2c3e4700dbf23
```

Profile validation and orchestration safeguards must continue to enforce this boundary.

## Safety Invariants

- Secrets never enter Git, proposals, reports, or public agent output.
- Remote writes require explicit confirmation.
- Publication requires an approval reference appropriate to the profile policy.
- Completed remote side effects are recorded and must not be repeated during recovery.
- No automatic remote retry.
- No automatic republish after an indeterminate publication result.
- No hidden Etsy activation or deactivation.
- No order creation.
- No protected-product modification.
- Artwork changes invalidate exact-hash approval.
- Final proposal changes invalidate final approval.

## Remaining Major Milestone

The main missing user-facing feature is a unified commerce command that chains the existing lower-level components into the preferred flow:

```text
jamesos commerce create --profile unitystitches --idea "..."
→ review and revise one complete listing package
jamesos commerce approve --job-id ... --proposal-sha256 ... --confirm
→ publish once and verify active on Etsy
```

The implementation should add:

- a complete immutable `CommerceProposal`
- canonical proposal hashing
- a listing-review HTML page with real mockups
- one final approval for UnityStitches
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

Runtime state, profiles, artwork, OAuth files, and reports live outside Git under `~/JamesOSData/JamesOS` and must be synchronized securely before continuing on another machine.
