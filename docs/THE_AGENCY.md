# The Agency

The Agency is JamesOS's local-first agent catalog and lifecycle manager. It is the place where users discover agents, inspect what they can do, hire them into **Your Team**, configure them, grant permissions and secret handles, place them **On Duty**, review activity, move them **Off Duty**, and release them.

The Agency does not replace Agent OS. It manages the human-facing lifecycle around agents, while Agent OS performs capability routing and enforces runtime approval, tool, secret, protected-resource, side-effect, retry, and durable-run policies.

## Why The Agency exists

Specialized agents are more useful when their authority is visible and bounded.

The Agency makes these questions explicit:

- Who published this agent?
- What capabilities does it provide?
- What tasks does it accept?
- What permissions and secret handles does it require?
- What side effects can it request?
- Which platforms and JamesOS versions does it support?
- Is required setup complete?
- Is the agent On Duty, Off Duty, degraded, or not hired?
- What lifecycle activity has occurred?

Discovering an agent does not install or execute it. Hiring an agent does not grant every permission. Configuring an agent does not approve a future consequential action.

## Available agents

JamesOS currently distinguishes between agents that are available in the checked-in Agency catalog and built-in runtime agents that support workflows but do not yet have their own standalone Agency package.

### Available in the checked-in catalog

#### Commerce Agent

- **Agent ID:** `jamesos.commerce`
- **Category:** Commerce
- **Status:** available to discover and hire
- **Purpose:** coordinates approval-first product and listing workflows
- **Primary capability:** `commerce.product_pipeline`
- **Configuration:** requires a private commerce profile reference
- **Safety:** private shop identity, credentials, account IDs, product IDs, and protected resources remain outside the public agent manifest

The Commerce Agent coordinates work. Provider- and marketplace-specific actions are delegated through narrower runtime agents and guarded tools.

#### Example Agent

- **Agent ID:** `jamesos.example`
- **Category:** HomeOps / example
- **Status:** available to discover and hire
- **Purpose:** demonstrates the complete Agency lifecycle safely
- **Primary capability:** `example.local_summary`
- **Configuration:** typed string, integer, enum, boolean, and URL examples
- **Safety:** no required secrets or consequential side effects

The Example Agent is the reference implementation for developers learning how manifests, configuration, readiness, and lifecycle state work.

### Built-in runtime agent foundations

#### CareerAgent

- ingests provider-neutral job records from local or approved sources
- normalizes and deduplicates opportunities
- ranks jobs with deterministic explanations
- prepares truthful application packets
- does not submit applications

CareerAgent is implemented in the runtime. A dedicated Agency manifest and polished Jade career workflow remain future work.

#### PrintifyAgent

- owns guarded provider-facing product capabilities
- supports product draft and publication-related operations through declared capabilities
- remains subordinate to commerce ownership, approval, protected-resource, and one-attempt rules

PrintifyAgent is currently used as a built-in commerce specialist rather than a separately hired catalog entry.

#### EtsyAgent

- owns marketplace reads and listing-state transitions
- supports listing resolution, deactivation, and final-state verification
- does not receive authority merely because a commerce proposal exists

EtsyAgent is currently used as a built-in commerce specialist rather than a separately hired catalog entry.

## How agents work together

```text
Jade or user intent
→ coordinating agent or Planner
→ AgentRequest / Job Queue
→ capability-routed specialist agent
→ ApprovalPolicy and ToolBroker
→ explicit confirmation when required
→ one-attempt side effect
→ verification and durable evidence
```

A common commerce composition is:

```text
CommerceAgent
├── PrintifyAgent
└── EtsyAgent
```

The coordinating agent owns the workflow and proposal. Specialist agents own narrow provider or marketplace capabilities. Private shops are `commerce_shop` profiles, not public agents.

## Lifecycle

Installation and configuration are intentionally separate:

```text
Discover
→ inspect manifest, publisher, capabilities, permissions, secrets, side effects, and compatibility
→ Hire / install
→ configure non-secret settings
→ grant required and optional permissions
→ create or select opaque secret handles
→ grant handles to declared secret requirements
→ verify readiness
→ place On Duty
→ monitor health and activity
→ move Off Duty or Release
```

### Discover

The current `DirectoryCatalogProvider` reads checked-in JSON manifests. It performs no network access, package acquisition, or code execution.

A future GitHub-backed catalog may implement the same read-only provider contract. Catalog discovery must remain separate from package installation.

### Hire

Hiring creates a local Agency record for the reviewed manifest. It does not silently install third-party packages or grant permissions.

### Configure

Configuration stores validated non-secret settings. Supported field types include:

- string
- integer
- boolean
- enum
- URL

Secrets are not ordinary configuration values.

### Permissions

Required and optional permissions are stored separately from the manifest request. Required permissions must be granted before an agent can be placed On Duty.

### Secret handles

The Agency stores requirement-to-handle grants, never secret values. Secret status exposes only safe metadata such as the opaque handle and whether it is configured.

### On Duty and Off Duty

An agent cannot go On Duty while required configuration, permissions, or secret handles are missing. Moving an agent Off Duty preserves its configuration for later use.

### Release

Release is confirmation-gated. It removes the hired lifecycle record without treating release as authority to delete unrelated private data or credentials.

## Current implementation

`AgencyService` coordinates the Agency domain:

- versioned `PackageManifest` remains the runtime registration contract
- Agency metadata adds category, tags, typed configuration, permissions, secret requirements, platform support, and installation/media placeholders
- `DirectoryCatalogProvider` reads the local checked-in catalog
- `AgencyStore` atomically persists hired state under `~/JamesOSData/JamesOS/Agency/state.json`
- Agency state files use restrictive permissions
- `AgencySecretProvider` extends handle-based secret resolution
- readiness blocks On Duty state when required setup is incomplete
- lifecycle mutations preview by default and require explicit confirmation

The authenticated API is rooted at `/agency`. Jade includes Discover, Your Team, and manifest-driven management views.

## Jade experience

### Discover

- browse local catalog entries
- inspect publisher, version, category, description, tags, and installed status
- inspect requested capabilities, permissions, secrets, side effects, and compatibility
- preview and confirm Hire

### Your Team

- view hired agents
- see On Duty, Off Duty, degraded, or missing-setup status
- open the management experience

### Agent management

- Overview
- Configuration
- Permissions
- Secrets
- Activity

Configuration widgets are driven by the manifest schema rather than hard-coded for Commerce or another specific agent.

## Local API flow

```text
GET  /agency/catalog
POST /agency/agents/jamesos.example/hire       {"confirmed": true}
PUT  /agency/agents/jamesos.example/configuration
PUT  /agency/agents/jamesos.example/permissions
PUT  /agency/agents/jamesos.example/secrets
POST /agency/agents/jamesos.example/enable     {"confirmed": true}
GET  /agency/agents/jamesos.example/activity
POST /agency/agents/jamesos.example/disable    {"confirmed": true}
POST /agency/agents/jamesos.example/release    {"confirmed": true}
```

Use normal JamesOS API authentication. Never put plaintext secrets in configuration requests; create or select a secret handle and grant that handle to the declared requirement.

## Current limitations and next steps

The current Agency milestone is intentionally local and controlled.

Implemented:

- checked-in local catalog
- versioned manifests
- hire/release and enable/disable lifecycle
- typed configuration
- permission grants
- secret-handle grants
- readiness enforcement
- authenticated API
- Jade Discover and Your Team foundations
- contributor documentation and proposal templates

Still planned:

- standalone manifests for more built-in agents, including CareerAgent
- contributor-facing manifest validation command
- read-only GitHub-backed catalog
- publisher, provenance, compatibility, review, revocation, and signature metadata
- separately approval-gated package installers
- install/update/rollback evidence
- richer health and activity views

Track this work in:

- [Documentation and onboarding issue #2](https://github.com/thedorfer/JamesOS/issues/2)
- [Community submissions and trusted catalog issue #12](https://github.com/thedorfer/JamesOS/issues/12)

## Safety boundaries

- catalog parsing never executes code
- discovery does not imply installation
- installation does not grant execution authority
- configuration does not approve consequential actions
- plaintext secret values never enter manifests, Agency state, logs, or normal API responses
- private deployment identities remain outside Git
- permission or side-effect expansion requires fresh review
- required setup blocks On Duty state
- third-party package acquisition belongs behind a separate installer boundary
- agents remain subject to Job Queue and Agent OS approval rules

## Developer and operator guides

- [Building Agents](BUILDING_AGENTS.md)
- [Installing Agents](INSTALLING_AGENTS.md)
- [Configuring Agents](CONFIGURING_AGENTS.md)
- [Submitting Agents](AGENT_SUBMISSIONS.md)
- [Agent OS Architecture](AGENT_OS.md)
- [Prioritized Roadmap](ROADMAP.md)
