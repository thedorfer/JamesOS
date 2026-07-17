# JamesOS

JamesOS is a local-first personal operating system and agent platform. It turns one private, evolving knowledge base into a coordinated team of specialized agents that can help with work, business, creative projects, career goals, household tasks, research, and everyday decisions.

Instead of isolated chatbots that repeatedly start from scratch, JamesOS agents can share governed access to Evidence, the Knowledge Graph, Working Memory, the Job Queue, private profiles, tools, and approval history. Agents remain narrow, declared software components—not unrestricted bots.

**Jade** is the user-facing assistant. **[The Agency](docs/THE_AGENCY.md)** is where agents are discovered, hired, configured, granted permissions and secret handles, placed On Duty, monitored, moved Off Duty, and released.

JamesOS is evidence-aware and approval-first. Planning and preparation can be proactive, while consequential actions require explicit confirmation, bounded side effects, and durable verification.

## What works today

At the July 17, 2026 checkpoint:

- the complete Python suite passes **425 tests**
- the FastAPI backend and Flutter Jade client are established
- Evidence, Knowledge Graph, Working Memory, Reasoner, Planner, and local search foundations are implemented
- the approval-first Job Queue is implemented
- Agent OS provides capability routing, tool brokering, secret handles, run ledgers, approval policy, and one-attempt controls
- The Agency provides a checked-in local catalog, hire/release lifecycle, typed configuration, permission grants, secret-handle grants, readiness checks, API routes, and Jade management screens
- the Career Agent can ingest, normalize, rank, and prepare truthful local application packets without submitting them
- commerce supports design validation, exact-hash design approval, provider drafts, recovery, real mockups, listing validation, and immutable review proposals
- the core Scheduler supports one-time, hourly, daily, and weekly timezone-aware schedules that enqueue normal Job Queue work without executing agents directly
- project cleanup tooling safely audits and removes known generated caches and build output
- order creation remains disabled

See [Current Status](docs/CURRENT_STATUS.md) for the detailed checkpoint.

## Why specialized agents are valuable

- **Shared context:** agents work from one governed knowledge base instead of separate context silos.
- **Specialization:** each agent declares its purpose, capabilities, permissions, secrets, side effects, and limits.
- **Coordination:** agents can hand work through Agent OS requests and the Job Queue while preserving traceability.
- **Personalization without hard-coding:** private profiles hold preferences, policies, accounts, and protected resources outside Git.
- **Human control:** proposals can be prepared automatically, but approval-bound actions remain explicit.
- **Recoverability:** durable evidence and deterministic identities prevent duplicate or hidden side effects.

## The Agency

[The Agency](docs/THE_AGENCY.md) is the agent-management layer for JamesOS.

```text
Discover
→ inspect publisher, capabilities, permissions, secrets, side effects, and compatibility
→ Hire
→ configure non-secret settings
→ grant permissions and opaque secret handles
→ verify readiness
→ place On Duty
→ monitor activity
→ move Off Duty or Release
```

### Available in the checked-in Agency catalog

- **Commerce Agent** — coordinates approval-first commerce work using a selected private `commerce_shop` profile.
- **Example Agent** — a safe local example used to learn and test the Agency lifecycle.

### Built-in agent foundations

- **CareerAgent** — local job ingestion, ranking, and truthful application-packet preparation.
- **PrintifyAgent** — guarded provider-facing product capabilities used by commerce workflows.
- **EtsyAgent** — marketplace reads, listing-state transitions, and final-state verification used by commerce workflows.

The catalog and runtime are deliberately distinct. An agent can exist as a built-in runtime foundation before it receives a standalone Agency manifest and user-facing package. The Agency page tracks that distinction and the current availability of each agent.

Private shop identities are profiles, not public agents. Shop-specific policies, account IDs, protected resources, credentials, and deployment state remain under `~/JamesOSData/JamesOS`.

## Core architecture

```text
Evidence
→ indexes, reports, and timeline
→ Knowledge Graph and Working Memory
→ Reasoner and Planner
→ Jade and specialized agents
```

```text
User intent or schedule
→ Planner, coordinating agent, or Scheduler
→ Job Queue or AgentRequest
→ capability-routed specialized agent
→ approval policy
→ explicit confirmation when required
→ one-attempt side effect
→ verification and durable evidence
```

The Scheduler decides **when** declarative work becomes due and enqueues it. It does not execute agents, bypass approvals, or perform provider actions itself.

## Current product priorities

### P0 — Finish the active vertical slice

1. Complete the current real commerce product through final marketplace verification without creating an order.
2. Keep Python and Flutter validation green.

### P1 — Make the foundations easy to use

1. Complete the unified `jamesos commerce` flow: guided preparation, revision, one immutable final approval, publish once, and final-state verification (#9, #15).
2. Build the Career Agent review dashboard and human-approved application handoff (#13).
3. Improve Agency onboarding, manifest validation, trusted catalog metadata, and contributor tooling (#2, #12).
4. Add a persistent scheduler runner and Jade schedule management without weakening Job Queue approval rules (#17).
5. Improve Jade navigation, status visibility, and recovery guidance.

### P2/P3 — Controlled expansion

- read-only remote Agency catalog and separately approved installers
- phone ingestion and evidence synchronization
- additional print-on-demand and publishing providers
- HomeOps, teaching, research, reporting, marketing, and lead-generation agents
- scheduled commerce generation after the one-product flow is stable

See the [prioritized roadmap](docs/ROADMAP.md).

## Commerce workflow

The target experience is:

```text
idea
→ local design and non-public provider preparation
→ real mockups and complete listing metadata
→ one immutable review proposal
→ revise as needed
→ one exact final approval
→ publish once
→ verify the configured final state
```

Phase 1A now compiles a read-only immutable proposal for an existing prepared job:

```bash
python scripts/jamesos.py commerce prepare --job-id JOB_ID
python scripts/jamesos.py commerce status --job-id JOB_ID
python scripts/jamesos.py commerce review --job-id JOB_ID
```

See [Unified Commerce Workflow](docs/UNIFIED_COMMERCE_WORKFLOW.md).

## Scheduling foundation

The Scheduler currently supports declarative one-time, anchored hourly, daily local-time, and weekly local-time schedules with IANA timezones, DST rules, misfire handling, and deterministic occurrence identities.

```bash
python scripts/jamesos.py schedule list
python scripts/jamesos.py schedule preview --schedule-id SCHEDULE_ID --count 5
python scripts/jamesos.py schedule tick
```

Mutations and enqueue operations preview by default and require explicit confirmation. See [Scheduler](docs/SCHEDULER.md).

## Agent developer path

```text
Open Agent Proposal issue
→ scope and safety review
→ contributor agreement
→ implement runtime agent and Agency manifest
→ add tests and documentation
→ submit focused pull request
→ code, security, privacy, and compatibility review
→ checked-in catalog inclusion
```

Start here:

- [The Agency](docs/THE_AGENCY.md)
- [Building Agents](docs/BUILDING_AGENTS.md)
- [Installing Agents](docs/INSTALLING_AGENTS.md)
- [Configuring Agents](docs/CONFIGURING_AGENTS.md)
- [Submitting Agents](docs/AGENT_SUBMISSIONS.md)
- [Agent OS Architecture](docs/AGENT_OS.md)

## Common development commands

```bash
python -m unittest discover tests
python scripts/project_cleanup.py audit
python scripts/project_cleanup.py clean-caches
```

```bash
cd apps/jade_app
flutter analyze
flutter test
flutter run -d linux
```

## Safety boundaries

- Secrets and deployment-specific profiles live outside Git under `~/JamesOSData/JamesOS`.
- Consequential external actions require explicit confirmation.
- No automatic retry of remote writes.
- No hidden publication, activation, deactivation, sending, or submission.
- No order creation from the product-orchestration path.
- Protected resource identifiers belong in private local profiles.
- Artwork changes invalidate exact-hash artwork approval.
- Proposal changes invalidate final proposal approval.
- Scheduled jobs retain normal Job Queue and Agent OS approval requirements.
- Imported text is untrusted data and cannot override JamesOS policy.
- Discovery does not imply installation, and installation does not grant execution authority.

## Documentation

- [Current Status](docs/CURRENT_STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [The Agency](docs/THE_AGENCY.md)
- [Agent OS](docs/AGENT_OS.md)
- [Unified Commerce Workflow](docs/UNIFIED_COMMERCE_WORKFLOW.md)
- [Scheduler](docs/SCHEDULER.md)
- [Job Search Agent](docs/JOB_SEARCH_AGENT.md)
- [Creative Studio Roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)
- [Project Cleanup](docs/PROJECT_CLEANUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Control Center](docs/CONTROL_CENTER.md)
- [Phone Ingestion](docs/PHONE_INGESTION.md)
- [Desktop Setup](docs/SETUP_DESKTOP.md)
- [Integrations](docs/INTEGRATIONS.md)

## License

JamesOS is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use requires separate written permission from James Allendoerfer.

See [NOTICE](NOTICE) and [CONTRIBUTING.md](CONTRIBUTING.md).
