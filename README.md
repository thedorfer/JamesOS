# JamesOS

JamesOS is a local-first personal operating system and agent platform. It combines a Python/FastAPI backend, local evidence ingestion, Knowledge Graph and Working Memory, a Flutter client named Jade, a durable Job Queue, an Agent OS runtime, and guarded automation for creative commerce.

The project is evidence-aware and approval-first. JamesOS can reason over local notes, imported ChatGPT history, email and calendar evidence, work records, phone events, reports, tickets, creative assets, provider drafts, and marketplace listing state. Consequential actions require explicit review, confirmation, and durable side-effect records.

## Current Status

At the July 16, 2026 checkpoint:

- `362` tests pass
- provider draft creation, recovery, mockup review, metadata updates, and guarded publication are implemented
- marketplace OAuth, listing reads, deactivation, inactive verification, and active-state verification are implemented
- configurable `single_final` and `staged` approval modes are implemented
- configurable marketplace final states `active` and `inactive` are implemented
- order creation remains disabled
- the preferred unified `idea → complete listing preview → approve once → live` CLI is the next major milestone

Read these first:

- [Current project status](docs/CURRENT_STATUS.md)
- [Agent OS architecture](docs/AGENT_OS.md)
- [Creative Studio roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)

## What JamesOS Does

- Runs a local FastAPI API for Jade and integrations.
- Keeps human notes in `~/Notes`.
- Keeps machine-owned data in `~/JamesOSData`.
- Builds local evidence into search indexes, reports, timelines, Working Memory, and Knowledge Graph pages.
- Lets Jade answer from local context instead of guessing.
- Uses Planner to turn intent into proposed work without silently executing it.
- Provides a durable Job Queue for approval-first automation.
- Provides a reusable Agent OS with capability routing, approval policies, run ledgers, tool brokering, and secret handles.
- Provides a Control Center for health, integrations, jobs, storage, and automation readiness.
- Supports Android phone ingestion through Tasker or desktop/laptop pull alternatives.
- Provides a Flutter Jade app for Linux and Android.
- Supports local design generation, candidate review, exact-hash approval, provider drafts, real mockup retrieval, and marketplace workflows.
- Supports generic commerce-shop profiles so deployment policy remains configuration rather than agent code.
- Keeps provider, marketplace, approval, and recovery logic independently testable.

## Core Architecture

The local reasoning path is:

```text
Evidence
→ indexes / reports / timeline
→ Knowledge Graph / Working Memory
→ Reasoner
→ Jade UI / API
```

The guarded automation path is:

```text
User intent
→ Planner / Commerce orchestration
→ Job Queue or AgentRequest
→ capability-routed agents
→ approval policy
→ explicit confirmation
→ one-attempt external action
→ verification and durable evidence
```

Evidence includes notes, imported ChatGPT exports, email archives, calendar imports, phone events, reports, timelines, attachments, design candidates, product draft packages, provider identifiers, mockups, and marketplace listing state.

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
- one-attempt side-effect controls

Current commerce agents:

```text
CommerceAgent
├── PrintifyAgent
└── EtsyAgent
```

The agents are bounded software components, not separate chatbots. The CommerceAgent coordinates workflows, the PrintifyAgent owns provider-facing capabilities, and the EtsyAgent owns marketplace reads and state transitions. Shops and deployments are represented by private local `commerce_shop` profiles rather than hard-coded public agent definitions.

See [Agent OS architecture](docs/AGENT_OS.md) for capabilities, task graphs, approval behavior, and recovery rules.

## Approval-First Automation

The Job Queue stores durable jobs under:

```text
~/JamesOSData/JamesOS/Queue/pending
~/JamesOSData/JamesOS/Queue/in_progress
~/JamesOSData/JamesOS/Queue/processed
~/JamesOSData/JamesOS/Queue/failed
```

Remote writes require explicit confirmation. Remote attempts are recorded, limited to one automatic attempt, and are not silently retried.

Approval modes are profile-configurable:

- `single_final`
- `staged`

Marketplace final states are independently configurable:

- `active`
- `inactive`

A typical single-final profile can use:

```json
{
  "approval_mode": "single_final",
  "marketplace_final_state": "active",
  "human_review_location": "jamesos_listing_preview",
  "preapproval_provider_draft_allowed": true,
  "publish_policy": "publish_active_after_approval"
}
```

A typical single-final flow is:

```text
idea
→ generate and validate artwork
→ create or update a non-public provider draft
→ retrieve real mockups
→ prepare complete marketplace listing metadata
→ display one immutable listing proposal
→ revise as needed
→ approve once
→ publish once
→ verify the listing is active
```

Candidate selection and revision requests are editing steps, not final approval.

## Creative Commerce

The current product orchestrator supports:

- prompt-to-brief parsing
- provider catalog and variant resolution
- local design candidate generation
- exact phrase enforcement
- transparency, dimensions, safe-bound, and uniqueness checks
- human review sheets
- exact candidate SHA-256 approval
- garment-specific contrast assessment
- universal-contrast design repair
- guarded artwork upload and product creation
- failed-create recovery without duplicate side effects
- exact mockup retrieval for selected variants
- artwork-ID, placement, variant, and front-only verification
- listing metadata preparation
- guarded publication
- marketplace listing resolution
- listing deactivation for staged mode
- active-state verification for direct-live mode

### Current diagnostic CLI

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

Mutating commands default to dry-run behavior unless their explicit confirmation flag is supplied.

The next user-facing milestone is a unified commerce command with one complete listing preview and one final approval.

## Safety Boundaries

- Secrets and deployment-specific profiles live outside Git under `~/JamesOSData/JamesOS`.
- No automatic remote retries.
- No duplicate product creation during recovery.
- No automatic republish after an indeterminate result.
- No hidden marketplace activation or deactivation.
- No order creation from the product-orchestration path.
- Protected resource identifiers belong in private local profiles, not public documentation.
- Artwork changes invalidate exact-hash artwork approval.
- Proposal changes invalidate final proposal approval.

## Control Center

The Control Center summarizes readiness without taking external action:

```text
GET /control-center
GET /control-center/health
GET /control-center/services
GET /control-center/integrations
GET /control-center/jobs
GET /control-center/storage
GET /control-center/summary
```

Generated report:

```text
~/JamesOSData/JamesOS/Reports/Control Center.md
```

## Jade Modes

- `Chat`: default conversational mode with automatic local context detection.
- `Work`: prioritizes work context, tickets, Knowledge Graph, email context, reports, and deployments.
- `Private`: uses local context but should not persist chat or write memory notes.

## Repository Shape

```text
jamesos/                 Python backend, services, agents, and integrations
scripts/                 CLI helpers and maintenance commands
apps/jade_app/           Flutter Jade client
docs/                    Architecture, setup, integration, status, and roadmap docs
tests/                   Python regression tests
```

## Common Commands

From the repository root:

```bash
python3 -m py_compile jamesos/services/*.py scripts/*.py
python3 -m unittest discover tests
```

Run the API server:

```bash
python3 scripts/api_server.py
curl http://localhost:8787/health
```

Flutter app:

```bash
cd apps/jade_app
flutter analyze
flutter run -d linux
```

## License

JamesOS is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md).

Noncommercial use, modification, and redistribution are permitted only under the terms of that license. Commercial use requires separate written permission from James Allendoerfer.

This is a source-available license and is not an open-source license. See [NOTICE](NOTICE) for the required copyright and licensing notice, and [CONTRIBUTING.md](CONTRIBUTING.md) for the current contribution policy.

## Documentation

- [Current Status](docs/CURRENT_STATUS.md)
- [Agent OS](docs/AGENT_OS.md)
- [The Agency](docs/THE_AGENCY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Desktop setup](docs/SETUP_DESKTOP.md)
- [ComfyUI setup](docs/COMFYUI_SETUP.md)
- [ComfyUI service](docs/COMFYUI_SERVICE.md)
- [Model Registry](docs/MODEL_REGISTRY.md)
- [Workflow Manager](docs/WORKFLOW_MANAGER.md)
- [Image Worker](docs/IMAGE_WORKER.md)
- [Design Planner](docs/DESIGN_PLANNER.md)
- [Design Critic](docs/DESIGN_CRITIC.md)
- [Design Runs](docs/DESIGN_RUNS.md)
- [Recipe Library](docs/RECIPE_LIBRARY.md)
- [Design DNA](docs/DESIGN_DNA.md)
- [Print Readiness Scoring](docs/PRINT_READINESS_SCORING.md)
- [Print-Ready Design Artifact](docs/PRINT_READY_DESIGN_ARTIFACT.md)
- [Brand Registry](docs/BRAND_REGISTRY.md)
- [POD Provider Registry](docs/POD_PROVIDER_REGISTRY.md)
- [Creative Foundations](docs/CREATIVE_FOUNDATIONS.md)
- [Asset Packs](docs/ASSET_PACKS.md)
- [Integrations](docs/INTEGRATIONS.md)
- [Control Center](docs/CONTROL_CENTER.md)
- [Planner](docs/PLANNER.md)
- [Workers](docs/WORKERS.md)
- [Knowledge Graph editing roadmap](docs/KNOWLEDGE_GRAPH_EDITING.md)
- [Phone ingestion](docs/PHONE_INGESTION.md)
- [Phone ingestion via Tasker](docs/PHONE_INGESTION_TASKER.md)
- [Creative Studio roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)
- [Creative Intelligence](docs/CREATIVE_INTELLIGENCE.md)
- [Etsy read-only performance](docs/ETSY_READONLY_PERFORMANCE.md)
- [API](docs/api.md)
- [CLI](docs/cli.md)
