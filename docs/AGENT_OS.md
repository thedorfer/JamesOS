# JamesOS Agent OS

_Last updated: July 16, 2026_

JamesOS includes an internal Agent OS for coordinating specialized capabilities without giving any single component unrestricted access to external services.

## Why Agents Exist

The agents are not separate chatbots. They are bounded software components that own narrow capabilities and cooperate through typed requests, plans, approvals, and durable run records.

The goals are:

- keep Printify, Etsy, creative generation, and orchestration logic separated
- make consequential actions reviewable
- bind approvals to exact artifacts or complete proposals
- prevent accidental duplicate uploads, products, publications, or state changes
- preserve enough evidence to recover safely after partial failures
- support multiple shops through configuration rather than duplicated code

## Runtime Components

### AgentRegistry

Registers agents and maps capabilities to the agent that owns them.

### AgentRunner

Receives an `AgentRequest`, finds the correct agent, evaluates approval requirements, executes the plan, runs follow-up tasks, records results, and returns public-safe output.

### AgentRequest

A typed request containing:

- task and run IDs
- workflow ID
- requested capability
- requesting agent
- target resources
- input payload
- risk level
- approval requirement
- idempotency key
- attempt limit

### AgentTaskRequest

A follow-up capability request emitted by one agent for another agent. This is how the CommerceAgent delegates Printify and Etsy work rather than instantiating clients directly.

### ToolBroker

Provides approved access to integrations such as Printify and Etsy. Agents request a named tool handle; they do not read credential files directly.

### SecretProvider

Resolves named secret handles from files outside Git. Secret values are not stored in profiles, proposals, reports, or public agent output.

### ApprovalPolicy

Blocks remote writes and publication unless the request carries the required approval reference. Exact-hash approvals can be required for artwork or a complete listing proposal.

### RunLedger

Records agent runs, attempts, child tasks, side effects, failures, and verification results so recovery can avoid repeating completed remote actions.

## Current Agents

## CommerceAgent

The CommerceAgent coordinates multi-step publication workflows.

Current capabilities:

- `commerce.workflow.publish_to_inactive_review`
- `commerce.workflow.publish_active_after_approval`

It delegates rather than calling provider clients directly.

### Active-after-approval flow

Used by UnityStitches:

```text
CommerceAgent
→ PrintifyAgent publishes the approved product once
→ EtsyAgent resolves and verifies the resulting listing
→ EtsyAgent verifies the listing state is active
```

### Staged-review flow

Available for other profiles:

```text
CommerceAgent
→ verifies Etsy readiness
→ PrintifyAgent publishes once
→ EtsyAgent deactivates the listing
→ EtsyAgent verifies inactive state
```

No automatic republish or automatic retry is allowed.

## PrintifyAgent

Owns Printify-facing product capabilities. It works through the product orchestrator and is constrained by explicit confirmation, idempotency records, protected-resource checks, and one-attempt limits.

Responsibilities include:

- product publication planning and execution
- exact target product verification
- use of the already-approved draft
- preservation of product and upload IDs
- blocking protected product changes
- never creating orders

The broader product orchestrator currently handles catalog resolution, artwork upload, product creation and update, variant configuration, mockup retrieval, and draft recovery. Those lower-level operations remain independently testable and are gradually being exposed through agent capabilities.

## EtsyAgent

Owns Etsy listing reads and state transitions.

Current capabilities include:

- `marketplace.listing.read`
- `marketplace.listing.deactivate`
- `marketplace.listing.verify_state`

Responsibilities include:

- confirming listing identity and shop ownership
- validating expected title when supplied
- reading current listing state
- changing an active listing to inactive for staged mode
- verifying active state for direct-live mode
- verifying inactive state after deactivation

OAuth credentials and refresh tokens remain outside Git.

## Profiles And Agents

A shop is a profile, not an agent.

UnityStitches is configured as a generic `commerce_shop` profile with bindings to:

```text
marketplace  → EtsyAgent
fulfillment  → PrintifyAgent
orchestrator → CommerceAgent
```

This lets the same agents support future shops with different policies.

## Configurable Approval Policies

Supported approval modes:

- `single_final`
- `staged`

Supported Etsy final states:

- `active`
- `inactive`

These settings are independent.

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

## Single-Final Approval

The target UnityStitches experience is:

```text
idea
→ local design generation and validation
→ non-public Printify draft
→ real Printify mockups
→ complete Etsy title, description, tags, price, variants, and placement
→ one immutable listing proposal
→ James approves once
→ publish once
→ verify Etsy listing is active
```

Selecting a candidate, requesting a design change, correcting contrast, or adjusting listing copy is editing, not final approval.

The final approval is intended to bind to a canonical proposal hash covering:

- exact artwork SHA-256
- Printify product and artwork IDs
- enabled variants
- placement
- mockups
- listing title
- listing description
- Etsy tags
- price
- destination shop
- expected Etsy final state

Any bound change invalidates the approval.

## Risk And Approval Model

Typical risk levels:

- read-only inspection
- local write
- remote write
- publication
- order/production action

Current policy:

- reads do not need explicit approval
- local review artifacts may be created without remote confirmation
- remote writes require explicit confirmation
- publication requires explicit approval
- order and production actions are not part of the product workflow

## Failure And Recovery Rules

Every external step has an idempotency key and an attempt limit of one.

Examples:

```text
artwork upload succeeds, product update fails
→ keep the upload ID
→ do not upload again automatically

Printify publication succeeds, Etsy lookup fails
→ mark the state indeterminate
→ do not republish

Etsy listing ID is known, deactivation fails
→ allow deactivation-only recovery
→ do not repeat publication
```

The execution record must identify which external writes were attempted, completed, failed, or remain indeterminate.

## Current Product-Orchestrator Relationship

The product orchestrator is the mature lower-level implementation currently used by the agents. It supports:

- prompt-to-product briefs
- design candidate generation
- exact phrase and safe-bound validation
- human artwork review
- exact-hash design approval
- garment contrast checks
- Printify upload, product creation, and product update
- variant and placement enforcement
- real mockup retrieval
- listing preparation
- guarded publication and Etsy review workflows
- recovery without duplicate completed side effects

The next step is to wrap these capabilities in a unified CommerceProposal workflow while keeping the lower-level commands available for diagnostics.

## Next Major Agent Milestone

Implement the preferred two-command user flow:

```bash
jamesos commerce create \
  --profile unitystitches \
  --idea "Supportive You Are Safe With Me rainbow heart shirt"

jamesos commerce approve \
  --job-id JOB_ID \
  --proposal-sha256 SHA256 \
  --confirm
```

Internally this should:

```text
CommerceAgent
├── request design generation and validation
├── request Printify draft creation or update
├── request exact mockup retrieval
├── request listing metadata generation
├── build immutable CommerceProposal
├── wait for one final approval
├── request one Printify publication
└── request Etsy active-state verification
```

The complete status and current product checkpoint are documented in [CURRENT_STATUS.md](CURRENT_STATUS.md).
