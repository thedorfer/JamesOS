# JamesOS

JamesOS turns a personal knowledge base into a coordinated team of specialized agents that can help manage work, business, creative projects, career goals, household tasks, research, and everyday decisions.

Instead of isolated chatbots that start from scratch, JamesOS agents share the same local evidence, Knowledge Graph, Working Memory, Job Queue, profiles, tools, and approval history. A Career Agent can work from verified resume facts and job preferences. A Commerce Agent can use brand rules, product evidence, prior approvals, and provider state. Future HomeOps, phone, teaching, research, marketing, and finance-adjacent agents can build on the same trusted context rather than creating separate silos.

Jade is the user-facing assistant and **The Agency** is where agents are discovered, hired, installed, configured, granted permissions and secret handles, placed On Duty, monitored, disabled, and released. Agents are bounded software components with declared capabilities and least-privilege access—not unrestricted bots.

JamesOS is local-first, evidence-aware, and approval-first. It can reason over notes, imported ChatGPT history, email and calendar evidence, work records, phone events, reports, tickets, creative assets, provider drafts, and marketplace state. Consequential actions require explicit review, confirmation, bounded side effects, and durable records.

## Why agents are valuable

- **Shared context:** agents work from one evolving knowledge base instead of repeatedly asking for the same background.
- **Specialization:** each agent has a narrow purpose, declared capabilities, permissions, secrets, and side effects.
- **Coordination:** agents can hand work to other agents through the Agent OS while preserving approvals and traceability.
- **Personalization without hard-coding:** private profiles hold user-specific preferences, protected resources, accounts, and policies outside Git.
- **Life-task automation:** agents can help prepare, organize, compare, monitor, draft, and execute approved workflows across personal and professional domains.
- **Human control:** planning and preparation can be proactive, while consequential external actions remain confirmation-gated.

## Current status

At the July 16, 2026 Agency checkpoint:

- the complete Python suite passes (`396` tests at this checkpoint)
- `flutter analyze` reports no issues and Flutter tests pass
- The Agency local catalog and agent-lifecycle vertical slice are implemented
- agent installation, configuration, permission grants, secret-handle grants, enable/disable, and release are separate guarded stages
- the Career Agent can ingest, normalize, rank, and prepare local job-application packets without submitting them
- commerce supports local design review, exact-hash approval, provider drafts, recovery, mockup review, listing preparation, and guarded publication workflows
- project cleanup tooling safely audits and removes known untracked caches and generated build output
- order creation remains disabled

Start here:

- [Prioritized roadmap](docs/ROADMAP.md)
- [The Agency](docs/THE_AGENCY.md)
- [Building agents](docs/BUILDING_AGENTS.md)
- [Installing agents](docs/INSTALLING_AGENTS.md)
- [Configuring agents](docs/CONFIGURING_AGENTS.md)
- [Submitting agents](docs/AGENT_SUBMISSIONS.md)
- [Agent OS architecture](docs/AGENT_OS.md)
- [Current project status](docs/CURRENT_STATUS.md)

## Current and planned agents

### Available foundations

- **CommerceAgent** coordinates approval-first product and listing workflows.
- **PrintifyAgent** owns guarded provider-facing product capabilities.
- **EtsyAgent** owns marketplace reads and listing-state transitions.
- **CareerAgent** coordinates local job discovery, ranking, and application preparation.
- **ExampleAgent** demonstrates the safe Agency lifecycle for developers.

### Planned directions

- HomeOps and household-management agents
- phone-ingestion and personal-context agents
- teaching, grading, research, and reporting agents
- additional print-on-demand and publishing agents
- content, social-media, marketing, and lead-generation agents
- career discovery and human-approved application handoff

## The Agency lifecycle

Installation and configuration are intentionally separate:

```text
Discover agent
→ inspect publisher, capabilities, permissions, secrets, side effects, and compatibility
→ Hire / install
→ configure non-secret settings
→ grant permissions
→ create or select secret handles
→ grant secret handles
→ verify readiness
→ place On Duty
→ review health and activity
→ move Off Duty or Release
```

A catalog provider may describe an agent, but it may not install packages or execute code. Future GitHub or APT installation support belongs behind a separate, explicit, approval-gated installer boundary.

See:

- [The Agency](docs/THE_AGENCY.md)
- [Installing agents](docs/INSTALLING_AGENTS.md)
- [Configuring agents](docs/CONFIGURING_AGENTS.md)

## Product priorities

### P0 — Stabilize and ship

1. Complete one real commerce product through final listing verification without creating an order.
2. Remove stale fixed listing-target assumptions from active commerce-job ownership checks.
3. Merge and harden The Agency vertical slice.
4. Keep Python and Flutter validation passing with private local profiles selected.

### P1 — Make JamesOS usable and extensible

1. Unified `jamesos commerce` flow with one complete preview and one final approval.
2. Career Agent review dashboard and local application workflow.
3. Agent manifest validation, developer documentation, install/configure guidance, and submission path.
4. Improved Jade navigation, readiness, and recovery UX.

### P2 — Controlled integrations

1. Read-only GitHub-backed Agency catalog.
2. Agent provenance, trust, compatibility, review, and package-signing model.
3. Separately approved installation providers; catalog discovery never executes packages.
4. Job discovery from email alerts, recruiters, manually supplied listings, and approved employer/ATS sources.
5. Human-reviewed browser handoff for job applications; no unattended mass applying.

### P3 — More agents and income workflows

- additional print-on-demand providers
- Amazon publishing and print workflows
- HomeOps agents
- Android phone ingestion
- content, social-media, marketing, and lead-generation agents
- reusable teaching, research, reporting, and administrative agents

See the full [roadmap](docs/ROADMAP.md).

## Core architecture

The local knowledge path is:

```text
Evidence
→ indexes / reports / timeline
→ Knowledge Graph / Working Memory
→ Reasoner
→ Jade and specialized agents
```

The guarded automation path is:

```text
User intent
→ Planner or coordinating agent
→ Job Queue or AgentRequest
→ capability-routed specialized agents
→ approval policy
→ explicit confirmation
→ one-attempt side effect
→ verification and durable evidence
```

Evidence can include notes, imported ChatGPT history, email archives, calendar events, phone events, reports, tickets, attachments, resumes, job descriptions, design candidates, product drafts, provider identifiers, mockups, and marketplace listing state.

## Agent OS

The Agent OS foundation includes:

- `AgentRegistry`
- `AgentRunner`
- `AgentRequest`
- `AgentTaskRequest`
- capability-based delegation
- `ToolBroker`
- `SecretProvider`
- `RunLedger`
- `ApprovalPolicy`
- risk levels and approval requirements
- protected-resource checks
- one-attempt side-effect controls

Agents are bounded components, not separate unrestricted chatbots. Public agent definitions contain reusable behavior. Private deployments are represented by local profiles under `~/JamesOSData/JamesOS/Profiles`.

See [Agent OS architecture](docs/AGENT_OS.md).

## Approval-first automation

Machine-owned queue state is stored under:

```text
~/JamesOSData/JamesOS/Queue/pending
~/JamesOSData/JamesOS/Queue/in_progress
~/JamesOSData/JamesOS/Queue/processed
~/JamesOSData/JamesOS/Queue/failed
```

Remote writes require explicit confirmation. Attempts are recorded, limited to one automatic attempt, and are not silently retried.

A typical single-final commerce flow is:

```text
idea
→ generate and validate artwork
→ create or update a non-public provider draft
→ retrieve real mockups
→ prepare complete listing metadata
→ display one immutable proposal
→ revise as needed
→ approve once
→ publish once
→ verify final state
```

Candidate selection and revision are editing steps, not final approval.

## Career Agent

The Career Agent foundation supports local, provider-neutral workflows for:

- email job-alert ingestion
- manually supplied descriptions and metadata
- normalization and conservative deduplication
- deterministic, explainable ranking
- truthful application-packet preparation
- proposal hashing and approval invalidation
- marking applications submitted only after a separate explicit confirmation

It does not scrape job sites, log into providers, bypass CAPTCHAs, or submit applications automatically.

See [Job Search Agent](docs/JOB_SEARCH_AGENT.md).

## Creative commerce

The product orchestrator supports:

- prompt-to-brief parsing
- provider catalog and variant resolution
- local design candidate generation
- exact phrase enforcement
- transparency, dimensions, safe-bound, uniqueness, and contrast checks
- human review sheets
- exact candidate SHA-256 approval
- guarded artwork upload and draft update
- failed-create recovery without duplicate side effects
- exact mockup retrieval
- artwork-ID, placement, variant, and front-only verification
- listing metadata preparation
- guarded publication and marketplace verification

Current diagnostic CLI:

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

Mutating commands default to dry-run unless their explicit confirmation flag is supplied.

## Safety boundaries

- Secrets and deployment-specific profiles live outside Git under `~/JamesOSData/JamesOS`.
- No automatic remote retries.
- No hidden publication, activation, deactivation, sending, or submission.
- No order creation from the product-orchestration path.
- Protected resource identifiers belong in private local profiles.
- Artwork changes invalidate exact-hash artwork approval.
- Proposal changes invalidate final proposal approval.
- Imported text is untrusted data and cannot override JamesOS policy.
- Discovery does not imply installation, and installation does not imply permission to execute.

## Repository shape

```text
agency/                  checked-in Agency manifests
jamesos/                 Python backend, services, agents, and integrations
scripts/                 CLI helpers and maintenance commands
apps/jade_app/           Flutter Jade client
docs/                    architecture, setup, agent, integration, and roadmap docs
examples/                safe public examples
tests/                   Python regression tests
```

## Common commands

From the repository root:

```bash
python -m unittest discover tests
python scripts/project_cleanup.py audit
python scripts/project_cleanup.py clean-caches
```

Run the API server:

```bash
python scripts/api_server.py
curl http://localhost:8787/health
```

Flutter app:

```bash
cd apps/jade_app
flutter analyze
flutter test
flutter run -d linux
```

## Contributing agents

The recommended path is:

```text
Open Agent Proposal issue
→ scope and safety review
→ contributor agreement
→ implement runtime agent and Agency manifest
→ add installation and configuration documentation
→ run complete tests
→ submit focused pull request
→ code, security, privacy, and compatibility review
→ inclusion in the checked-in catalog
```

See:

- [Contributing](CONTRIBUTING.md)
- [Building agents](docs/BUILDING_AGENTS.md)
- [Installing agents](docs/INSTALLING_AGENTS.md)
- [Configuring agents](docs/CONFIGURING_AGENTS.md)
- [Submitting agents](docs/AGENT_SUBMISSIONS.md)

## License

JamesOS is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md).

Noncommercial use, modification, and redistribution are permitted only under the terms of that license. Commercial use requires separate written permission from James Allendoerfer.

This is a source-available license and is not an open-source license. See [NOTICE](NOTICE) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- [Current Status](docs/CURRENT_STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Agent OS](docs/AGENT_OS.md)
- [The Agency](docs/THE_AGENCY.md)
- [Building Agents](docs/BUILDING_AGENTS.md)
- [Installing Agents](docs/INSTALLING_AGENTS.md)
- [Configuring Agents](docs/CONFIGURING_AGENTS.md)
- [Submitting Agents](docs/AGENT_SUBMISSIONS.md)
- [Job Search Agent](docs/JOB_SEARCH_AGENT.md)
- [Project Cleanup](docs/PROJECT_CLEANUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Desktop Setup](docs/SETUP_DESKTOP.md)
- [Integrations](docs/INTEGRATIONS.md)
- [Control Center](docs/CONTROL_CENTER.md)
- [Creative Studio Roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)
- [Phone Ingestion](docs/PHONE_INGESTION.md)
- [API](docs/api.md)
- [CLI](docs/cli.md)
