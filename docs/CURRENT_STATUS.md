# JamesOS Current Status

_Last updated: July 17, 2026_

JamesOS is a local-first personal operating system and agent platform. It now includes a working assistant foundation, approval-first Job Queue, Agent OS, The Agency lifecycle manager, guarded commerce tooling, a Career Agent foundation, an immutable commerce proposal compiler, and a timezone-aware scheduling service.

## Snapshot

- Complete Python suite at checkpoint: **425 passing tests**
- Runtime data root: `~/JamesOSData/JamesOS`
- Human-authored notes root: `~/Notes`
- Secrets and deployment-specific profiles remain outside Git
- Order creation remains disabled

## Platform foundations

### Jade and local assistant platform

- FastAPI backend
- Flutter Jade client
- local evidence ingestion and search
- Knowledge Graph and Working Memory
- Reasoner and Planner foundations
- durable approval-first Job Queue
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

Built-in runtime agent foundations:

- `CommerceAgent`
- `PrintifyAgent`
- `EtsyAgent`
- `CareerAgent`

Private shops are local `commerce_shop` profiles rather than hard-coded public agents.

### The Agency

The Agency provides the human-facing lifecycle around agents:

- checked-in local catalog
- versioned manifests
- Hire and Release
- On Duty and Off Duty
- typed non-secret configuration
- required and optional permission grants
- opaque secret-handle grants
- readiness enforcement
- atomic private lifecycle state
- authenticated `/agency` API
- Jade Discover, Your Team, and management views

Available checked-in catalog entries:

- Commerce Agent
- Example Agent

PrintifyAgent, EtsyAgent, and CareerAgent are built-in runtime foundations but are not yet standalone catalog packages.

See [The Agency](THE_AGENCY.md).

## Commerce status

### Implemented lower-level capabilities

The product orchestrator can:

- parse a product idea into a structured brief
- resolve provider blueprint, provider, colors, sizes, and variants
- generate and validate multiple local design candidates
- enforce exact phrase rendering
- validate transparency, dimensions, safe bounds, uniqueness, and contrast
- generate human review sheets
- bind design approval to an exact SHA-256
- upload approved artwork after explicit confirmation
- create or update a non-public provider draft
- recover from uncertain creation without duplicating completed side effects
- download exact provider mockups
- verify artwork ID, placement, enabled variants, pricing, and front-only configuration
- validate listing title, description, tags, and price
- identify the active product from job-local ownership evidence
- prepare guarded provider and marketplace plans
- publish through the provider only under explicit confirmation
- resolve and verify marketplace listing state

Remote actions are not automatically retried.

### Immutable proposal foundation

Phase 1A of the unified commerce workflow is implemented.

```bash
python scripts/jamesos.py commerce prepare --job-id JOB_ID
python scripts/jamesos.py commerce status --job-id JOB_ID
python scripts/jamesos.py commerce review --job-id JOB_ID
```

The proposal compiler:

- reuses the authoritative ownership, metadata, artwork, variant, placement, publication, and order checks
- creates a canonical deterministic proposal SHA-256
- binds artwork, mockups, listing metadata, price, variants, placement, destination, warnings, and expected final state
- separates public review data from private provider bindings
- archives superseded proposals
- marks only the newest proposal approval-eligible
- generates one local HTML review page
- stops at `awaiting_final_approval`
- performs no publication and creates no order

Remaining unified-commerce work:

- prepare a new product from one idea through one command
- guided revision
- exact proposal approval
- publish-once execution
- configured final-state verification
- Jade review and approval UI

Track this in issues #9 and #15.

## Career Agent status

The Career Agent foundation supports:

- provider-neutral local job ingestion
- normalized job records
- conservative deduplication
- deterministic and explainable ranking
- truthful application-packet preparation
- resume and proposal hashing
- approval invalidation when the packet changes
- explicit submitted-state tracking
- no external submission capability

Remaining work includes private career profile configuration, email-alert ingestion, Jade review workflow, follow-up tracking, and human-reviewed provider/browser handoff.

Track this in issue #13.

## Scheduler status

The core scheduling service foundation is implemented.

Supported triggers:

- one-time aware datetime
- anchored hourly interval
- daily local time
- weekly local time on selected weekdays

The scheduler provides:

- IANA timezone handling
- deterministic DST behavior
- injected clocks for testing
- preview-first create, enable, disable, and tick operations
- atomic private schedule and occurrence state
- deterministic occurrence identities
- restart-safe duplicate prevention
- `skip` and `fire_once` misfire policies
- idempotent Job Queue enqueue
- no direct agent execution

The scheduler decides when work is due and enqueues a normal Job Queue item. Scheduled work remains subject to its existing approval requirements.

Future work is tracked in issue #17:

- persistent bounded runner
- user-level systemd integration
- health and observability
- Jade schedule management
- condition watches and richer recurrence types

## Current lower-level commerce CLI

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

## Provider and marketplace integration

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

## Private runtime state

Live jobs, shop names, account identifiers, provider product identifiers, artwork hashes, protected-resource identifiers, OAuth files, review artifacts, proposals, schedule payloads, and execution reports belong under `~/JamesOSData/JamesOS` or another private deployment store. They must not be committed to the public repository.

## Safety invariants

- secrets never enter Git, public proposals, reports, or public agent output
- deployment-specific identities and identifiers remain outside Git
- consequential remote writes require explicit confirmation
- completed remote side effects are recorded and must not be repeated during recovery
- no automatic remote retry
- no hidden marketplace activation or deactivation
- no order creation
- no protected-resource modification
- artwork changes invalidate exact-hash approval
- bound proposal changes invalidate final approval
- scheduled jobs retain normal Job Queue and Agent OS approval requirements
- catalog discovery never executes code
- installation and configuration remain separate

## Next major milestones

1. Finish the current real commerce product through final marketplace verification without creating an order.
2. Complete guided commerce revision and exact publish-once approval.
3. Add the Career Agent review dashboard and approved opportunity ingestion.
4. Add contributor manifest validation and trusted Agency catalog metadata.
5. Add the persistent scheduler runner and Jade schedule management.

## Resume on another machine

```bash
cd ~/JamesOS
git pull --ff-only origin master
python -m unittest discover tests
```

Runtime state, private profiles, artwork, OAuth files, proposals, schedules, and reports live outside Git and must be synchronized securely before continuing on another machine.
