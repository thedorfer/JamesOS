# Jade Creative Studio Roadmap (historical phase record)

Status-sensitive claims in this document describe their original phase. Defer to [Current status](CURRENT_STATUS.md) for merged, branch-implemented, desktop-verified, and planned distinctions.

Jade Creative Studio is the creative automation surface for JamesOS. It creates reviewable local work packages and uses guarded provider and marketplace integrations.

## North Star

```text
idea
→ design plan
→ candidates
→ validation
→ provider draft
→ real mockups
→ complete listing proposal
→ approval
→ guarded publication
→ final-state verification
```

Private shop names, account identifiers, product identifiers, artwork, and deployment policies live outside the public repository.

## Phase 1: Foundations

Status: complete.

- Job Queue
- approval-gated job model
- server config and integration health foundation
- Control Center admin/readiness foundation
- architecture and roadmap docs

## Phase 2: Creative Studio Foundation

Status: complete.

- `jamesos/services/creative_studio.py`
- `scripts/creative_studio.py`
- local configuration under `~/JamesOSData/JamesOS`
- Creative Studio API routes
- Job Queue-backed creative jobs
- queue-backed pipeline stages

## Phase 3: Creative Review Shell

Status: foundation in place; polished user experience remains in progress.

- creative-job dashboard
- draft package viewer
- approve, reject, and regenerate actions
- source and evidence labels
- local asset browser
- explicit safety state for every draft

## Phase 4: Generic Product Pipeline

Status: lower-level foundations implemented.

- configurable product mix
- niche and compatibility rules
- title, tags, and description generation
- pricing notes
- provider catalog and blueprint resolution
- `needs_review` state
- approval requirements
- profile-driven shop policy

The public code must remain generic. Shop-specific product mixes, brand voice, niche choices, and account details belong in private local profiles.

## Phase 5: Local Image Generation

Status: approved local image generation and deterministic design rendering are available.

Active pieces:

- ComfyUI health checks
- Model Registry
- Workflow Manager
- Image Worker plans
- approved local execution
- generated assets under JamesOSData
- deterministic text and motif composition for exact phrase rendering
- transparency, bounds, resolution, uniqueness, and contrast checks
- human artistic review artifacts

ComfyUI is only an image engine. JamesOS owns the workflow, safety model, storage, validation, and approvals.

## Phase 6: Provider Draft Integration

Status: implemented and live-tested.

Capabilities:

- list shops and catalogs
- resolve blueprint, provider, colors, sizes, and variants
- upload approved artwork
- create or update a non-public product draft
- retrieve real mockups
- verify artwork ID, placement, variants, and front-only configuration
- recover without duplicating completed side effects

Rules:

- explicit confirmation for remote writes
- no automatic retry
- no duplicate product creation during recovery
- protected resources enforced from private profiles
- no order creation

## Phase 7: Marketplace Integration

Status: guarded capabilities implemented and live-tested.

Capabilities:

- OAuth authorization and refresh
- listing reads
- listing resolution after provider publication
- staged deactivation and inactive verification
- active-state verification

Rules:

- no publication without the required approval reference
- no hidden activation or deactivation
- no automatic republish after an indeterminate result
- no order fulfillment from the product workflow

## Phase 8: Agent OS

Status: foundation implemented.

```text
CommerceAgent
├── PrintifyAgent
└── EtsyAgent
```

The agents cooperate through typed requests, capability routing, approval policies, tool brokering, secret handles, run ledgers, and one-attempt controls.

Private shops are profiles, not agents.

## Phase 9: Unified Commerce Proposal

Status: next major milestone.

Target user experience:

```text
give idea
→ JamesOS generates design and creates a non-public provider draft
→ JamesOS retrieves real mockups and prepares the complete listing
→ user reviews and revises
→ user approves the immutable proposal once
→ JamesOS publishes once
→ JamesOS verifies the configured final marketplace state
```

Planned commands:

```bash
jamesos commerce create \
  --profile PRIVATE_PROFILE_ID \
  --idea "PRODUCT IDEA"

jamesos commerce approve \
  --job-id JOB_ID \
  --proposal-sha256 SHA256 \
  --confirm
```

The proposal should bind artwork, provider draft IDs, mockups, listing metadata, price, variants, placement, destination, and expected final state.

## Phase 10: Sales Intelligence

Status: read-only performance foundation exists.

Planned and active directions:

- product and niche performance
- seasonal timing
- pricing suggestions
- listing quality checks
- draft iteration recommendations
- provider-agnostic performance learning

Sales intelligence should advise first and request guarded actions only through the Agent OS.

## Safety Model

- local-first
- evidence-aware
- profile-configurable approvals
- exact-hash or proposal-hash approval binding
- no automatic external retry
- no duplicate completed side effects
- no hidden publication state changes
- no orders
- deployment-specific identities and identifiers outside Git
