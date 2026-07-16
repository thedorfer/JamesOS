# JamesOS Architecture

JamesOS is a local-first personal operating system and agent platform. It combines evidence ingestion, Knowledge Graph and Working Memory, Jade reasoning, a Flutter client, a Job Queue, an Agent OS runtime, and approval-first automation.

## Storage Model

JamesOS keeps human-authored notes and machine-owned data separate:

- Human notes: `~/Notes`
- Machine-owned data: `~/JamesOSData`

Generated reports, queues, imports, indexes, product drafts, attachment manifests, service config, private commerce profiles, credentials, and runtime identifiers belong under `~/JamesOSData` rather than the public repository.

## Evidence To Reasoning

```text
Evidence
→ indexes / reports / timeline
→ Knowledge Graph / Working Memory
→ Reasoner
→ Planner
→ Jade UI / API
```

Evidence sources include notes, imported ChatGPT history, email and calendar archives, phone events, attachments, reports, timelines, and private product draft packages.

The Planner proposes work but does not silently execute it. The Job Queue and Agent OS remain approval boundaries for consequential actions.

## Backend

The Python backend provides:

- FastAPI routes for Jade and integrations
- ingestion and import services
- search and typed indexes
- Knowledge Graph and memory services
- Job Queue operations
- Planner operations
- brand/profile registry operations
- agent routing and approval controls
- reports and health/config pages

The API is normally served by `scripts/api_server.py` on port `8787`.

## Jade Client

`apps/jade_app/` is the Flutter Jade client. Jade is the user-facing assistant and should stay concise, useful, and evidence-aware.

Visible modes:

- Chat
- Work
- Private

## Job Queue Backbone

Durable jobs live under:

- `~/JamesOSData/JamesOS/Queue/pending`
- `~/JamesOSData/JamesOS/Queue/in_progress`
- `~/JamesOSData/JamesOS/Queue/processed`
- `~/JamesOSData/JamesOS/Queue/failed`

Jobs record identity, status, approval requirements, payload, steps, logs, errors, and side-effect evidence.

## Agent OS

The Agent OS adds capability-routed execution over the queue and integration layer.

Core components:

- `AgentRegistry`
- `AgentRunner`
- `AgentRequest`
- `AgentTaskRequest`
- `ApprovalPolicy`
- `ToolBroker`
- `SecretProvider`
- `RunLedger`

Current commerce agents:

```text
CommerceAgent
├── PrintifyAgent
└── EtsyAgent
```

Agents are bounded software components. Private shop identities and deployment-specific policies are stored in local profiles outside Git.

## Profiles

A deployment is represented by a generic profile, not a hard-coded public agent.

A private `commerce_shop` profile may define:

- integration bindings
- secret handles
- approval mode
- expected final marketplace state
- draft policy
- pricing and listing policy references
- protected resources

Profile names, account identifiers, product identifiers, and credentials must not be committed publicly.

## Creative Commerce

The product orchestrator supports:

```text
idea
→ structured brief
→ design candidates
→ technical validation
→ human review
→ provider draft
→ real mockups
→ complete listing proposal
→ approval
→ guarded publication
→ marketplace verification
```

The lower-level implementation includes candidate generation, exact phrase validation, safe-bound checks, contrast validation, artwork upload, product creation/update, variant enforcement, mockup retrieval, listing preparation, publication, marketplace state handling, and recovery.

## Approval Model

Supported approval modes:

- `single_final`
- `staged`

Supported final states:

- `active`
- `inactive`

Any approval may be bound to an exact artwork hash or a canonical proposal hash. Changes invalidate the approval.

## Failure And Recovery

Every external action has an idempotency key and a one-attempt default.

Rules:

- preserve discovered remote IDs
- never silently retry remote writes
- never repeat completed side effects during recovery
- do not republish after an indeterminate publication result
- allow narrowly scoped recovery when the remaining action is known
- never create an order from the product-orchestration path

## Control Center

The Control Center summarizes API health, queue counts, agent/integration readiness, storage, and approval-needed jobs. It is observational and does not itself perform external writes.

## Public Repository Boundary

The public repository contains reusable platform code, schemas, agents, tests, and generic documentation.

The following belong outside Git:

- shop and brand names
- account and shop IDs
- product and listing IDs
- protected resource IDs
- OAuth files and secrets
- private product ideas and artwork
- live job checkpoints and execution reports
- deployment-specific profile files
