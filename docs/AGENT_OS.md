# JamesOS Agent OS

_Last updated: July 16, 2026_

JamesOS includes an internal Agent OS for coordinating specialized capabilities without giving any single component unrestricted access to external services.

## Why Agents Exist

The agents are not separate chatbots. They are bounded software components that own narrow capabilities and cooperate through typed requests, plans, approvals, and durable run records.

The goals are:

- keep provider, marketplace, creative generation, and orchestration logic separated
- make consequential actions reviewable
- bind approvals to exact artifacts or complete proposals
- prevent accidental duplicate uploads, products, publications, or state changes
- preserve enough evidence to recover safely after partial failures
- support multiple private deployments through configuration rather than duplicated code

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

A follow-up capability request emitted by one agent for another agent. This is how the CommerceAgent delegates provider and marketplace work rather than instantiating clients directly.

### ToolBroker

Provides approved access to integrations. Agents request a named tool handle; they do not read credential files directly.

### SecretProvider

Resolves named secret handles from files outside Git. Secret values are not stored in profiles, proposals, reports, or public agent output.

### ApprovalPolicy

Blocks remote writes and publication unless the request carries the required approval reference. Exact-hash approvals can be required for artwork or a complete listing proposal.

### RunLedger

Records agent runs, attempts, child tasks, side effects, failures, and verification results so recovery can avoid repeating completed remote actions.

## Current Agents

### CommerceAgent

The CommerceAgent coordinates multi-step publication workflows.

Current capabilities:

- `commerce.workflow.publish_to_inactive_review`
- `commerce.workflow.publish_active_after_approval`

It delegates rather than calling integration clients directly.

#### Active-after-approval flow

Available to profiles that publish live after final approval:

```text
CommerceAgent
→ PrintifyAgent publishes the approved product once
→ EtsyAgent resolves and verifies the resulting listing
→ EtsyAgent verifies the listing state is active
```

#### Staged-review flow

Available to profiles that require marketplace review before activation:

```text
CommerceAgent
→ verifies marketplace readiness
→ PrintifyAgent publishes once
→ EtsyAgent deactivates the listing
→ EtsyAgent verifies inactive state
```

No automatic republish or automatic retry is allowed.

### PrintifyAgent

Owns provider-facing product capabilities. It works through the product orchestrator and is constrained by explicit confirmation, idempotency records, protected-resource checks, and one-attempt limits.

Responsibilities include:

- product publication planning and execution
- exact target product verification
- use of the already-approved draft
- preservation of product and upload IDs
- blocking protected product changes
- never creating orders

The broader product orchestrator currently handles catalog resolution, artwork upload, product creation and update, variant configuration, mockup retrieval, and draft recovery. Those lower-level operations remain independently testable and are gradually being exposed through agent capabilities.

### EtsyAgent

Owns marketplace listing reads and state transitions.

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

A shop or deployment is a profile, not an agent.

Private local `commerce_shop` profiles can bind to:

```text
marketplace  → EtsyAgent
fulfillment  → PrintifyAgent
orchestrator → CommerceAgent
```

This lets the same public agent code support multiple private deployments with different policies while keeping identifying names, shop IDs, product IDs, and protected resources outside Git.

## Configurable Approval Policies

Supported approval modes:

- `single_final`
- `staged`

Supported marketplace final states:

- `active`
- `inactive`

These settings are independent.

A typical private profile can use:

```json
{
  "approval_mode": "single_final",
  "marketplace_final_state": "active",
  "human_review_location": "jamesos_listing_preview",
  "preapproval_provider_draft_allowed": true,
  "publish_policy": "publish_active_after_approval"
}
```

## Single-Final Approval

A generic single-final experience is:

```text
idea
→ local design generation and validation
→ non-public provider draft
→ real provider mockups
→ complete marketplace title, description, tags, price, variants, and placement
→ one immutable listing proposal
→ user approves once
→ publish once
→ verify the marketplace listing is active
```

Selecting a candidate, requesting a design change, correcting contrast, or adjusting listing copy is editing, not final approval.

The final approval is intended to bind to a canonical proposal hash covering:

- exact artwork SHA-256
- provider product and artwork IDs
- enabled variants
- placement
- mockups
- listing title
- listing description
- marketplace tags
- price
- destination marketplace account
- expected final state

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

provider publication succeeds, marketplace lookup fails
→ mark the state indeterminate
→ do not republish

marketplace listing ID is known, deactivation fails
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
- provider upload, product creation, and product update
- variant and placement enforcement
- real mockup retrieval
- listing preparation
- guarded publication and marketplace review workflows
- recovery without duplicate completed side effects

The next step is to wrap these capabilities in a unified `CommerceProposal` workflow while keeping the lower-level commands available for diagnostics.

## Next Major Agent Milestone

Implement a preferred two-command user flow:

```bash
jamesos commerce create \
  --profile PRIVATE_PROFILE_ID \
  --idea "PRODUCT IDEA"

jamesos commerce approve \
  --job-id JOB_ID \
  --proposal-sha256 SHA256 \
  --confirm
```

Internally this should:

```text
CommerceAgent
├── request design generation and validation
├── request provider draft creation or update
├── request exact mockup retrieval
├── request listing metadata generation
├── build immutable CommerceProposal
├── wait for one final approval
├── request one provider publication
└── request marketplace final-state verification
```

Deployment-specific profile names, credentials, shop IDs, product IDs, and checkpoints belong outside the public repository.
