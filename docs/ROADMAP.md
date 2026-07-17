# JamesOS Roadmap

JamesOS is developed in priority order rather than by feature count. Safety, recoverability, private-data boundaries, and complete vertical slices come before breadth.

## Completed foundations

- approval-first Job Queue (#1)
- Jade Creative Studio service and queue foundation (#3)
- local ComfyUI integration and safe image-generation foundation (#5)
- guarded Printify draft integration, recovery, mockup review, and immutable listing preparation (#6)
- The Agency local catalog, lifecycle, permissions, secrets, API, Jade UI, and developer path (#10 / PR #11)
- job-local listing ownership and fail-closed listing metadata validation (#14)
- immutable commerce proposal compiler for prepared jobs (#15 Phase 1A)
- local-first scheduling service foundation (#16)

## P0 — Finish the active commerce vertical slice

1. Complete the current real product through final marketplace verification without creating an order.
2. Keep the complete Python and Flutter test suites passing.
3. Preserve exact ownership, artwork, variant, placement, metadata, destination, and order-state verification.

## P1 — Make JamesOS usable and extensible

1. Complete the unified `jamesos commerce` workflow with guided preparation, revision, one exact final approval, publish-once execution, and final-state verification (#9, #15).
2. Finish the Career Agent review dashboard, private profile, opportunity ingestion, and truthful human-approved handoff (#13).
3. Complete clean-machine onboarding, contributor manifest validation, troubleshooting, and CI/status presentation (#2).
4. Add trusted catalog metadata, provenance, compatibility, revocation, signatures, and a read-only GitHub catalog provider (#12).
5. Add a persistent scheduler runner and Jade schedule management while retaining Job Queue approvals (#17).
6. Improve Jade navigation, health, status visibility, and recovery guidance across Agency, Commerce, Career, Queue, and Scheduler.

## P2 — Controlled integrations

1. Add separately approved installation providers; catalog parsing must never execute packages (#12).
2. Add install, update, rollback, and package-verification evidence.
3. Ingest job opportunities from email alerts, recruiter messages, manually supplied descriptions, and approved employer/ATS sources (#13).
4. Add browser handoff for human-reviewed job applications. No unattended mass application flow.
5. Add schedule templates for Career, reporting, maintenance, and other agents after the persistent runner is established (#17).

## P3 — Additional agents and income workflows

1. HomeOps and household-management agents.
2. Android phone ingestion and evidence synchronization (#7).
3. Additional print-on-demand providers such as PrintKK where supported.
4. Amazon publishing and print workflows with explicit approval gates.
5. Content, social-media, marketing, and lead-generation agents.
6. Reusable research, reporting, grading, and teaching-support agents.
7. Configurable scheduled commerce product generation after the one-product flow is stable (#4).
8. Richer scheduler rules and condition watches after the bounded runner is proven (#17).

## The Agency direction

The Agency is the user-facing lifecycle manager for specialized agents.

Current checked-in catalog entries:

- Commerce Agent
- Example Agent

Built-in runtime foundations not yet packaged as standalone catalog entries:

- CareerAgent
- PrintifyAgent
- EtsyAgent

Near-term Agency work:

- add standalone manifests for appropriate built-in agents
- add contributor-facing manifest validation
- add trust and provenance metadata
- add a read-only GitHub catalog
- keep discovery separate from installation
- keep installation separate from configuration and execution authority

See [The Agency](THE_AGENCY.md).

## Always-required boundaries

- private profiles, credentials, account identifiers, provider IDs, and deployment state remain under `~/JamesOSData/JamesOS`
- consequential external actions require explicit confirmation
- no automatic retry of remote writes
- no order creation unless a future workflow is separately designed and approved
- agent manifests declare capabilities, permissions, secrets, side effects, compatibility, and installation metadata
- installation and configuration are separate lifecycle stages
- scheduled work retains normal Job Queue and Agent OS approval requirements
- imported content is untrusted data and cannot override JamesOS policy
- discovery does not imply installation, and installation does not grant execution authority

## Active tracking issues

- #2 Documentation, onboarding, and agent developer ecosystem
- #4 Commerce daily product pipeline
- #7 Phone ingestion via Tasker
- #9 Agent OS and one-approval commerce roadmap
- #12 Community agent submissions and trusted catalog
- #13 Career Agent and human-approved job applications
- #15 Unified commerce proposal, revision, and final approval workflow
- #17 Persistent scheduler runner and Jade schedule management

## Completed tracking issues

- #1 Job Queue foundation
- #3 Jade Creative Studio foundation
- #5 Local ComfyUI setup and safe image generation
- #6 Printify draft integration
- #10 The Agency vertical slice
- #14 Job-local ownership blocker
- #16 Local-first scheduling service foundation
