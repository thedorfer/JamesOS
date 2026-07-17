# JamesOS Roadmap

JamesOS is developed in priority order rather than by feature count. Safety, recoverability, private-data boundaries, and complete vertical slices come before breadth.

## P0 — Stabilize and ship the current vertical slices

1. Complete one real commerce product from idea through final listing verification without creating an order.
2. Remove fixed deployment-specific listing-target assumptions from active commerce job ownership checks.
3. Merge The Agency local catalog, lifecycle, permissions, secrets, API, and Jade UI vertical slice.
4. Keep the complete Python and Flutter test suites passing with a private local profile selected.

## P1 — Make JamesOS usable and extensible

1. Provide a unified `jamesos commerce` workflow with one complete preview and one final approval.
2. Finish the Career Agent review dashboard and local application packet workflow.
3. Publish clear agent building, installation, configuration, and submission guides.
4. Add manifest validation and contributor-facing examples.
5. Improve Jade navigation, status visibility, and recovery guidance.

## P2 — Controlled integrations

1. Add a read-only GitHub-backed catalog provider for The Agency.
2. Define trust, compatibility, review, provenance, and package-signing rules for third-party agents.
3. Add separately approved installation providers; catalog parsing must never execute packages.
4. Ingest job opportunities from email alerts, recruiter messages, manually supplied descriptions, and approved employer/ATS sources.
5. Add browser handoff for human-reviewed job applications. No unattended mass application flow.

## P3 — Additional agents and income workflows

1. HomeOps and household-management agents.
2. Android phone ingestion and evidence synchronization.
3. Additional print-on-demand providers such as PrintKK where supported.
4. Amazon publishing and print workflows with explicit approval gates.
5. Content, social-media, marketing, and lead-generation agents.
6. Reusable research, reporting, and teaching-support agents.

## Always-required boundaries

- Private profiles, credentials, account identifiers, and deployment state remain under `~/JamesOSData/JamesOS`.
- Consequential external actions require explicit confirmation.
- No automatic retry of remote writes.
- No order creation unless a future workflow is separately designed and approved.
- Agent manifests declare capabilities, permissions, secrets, side effects, compatibility, and installation metadata.
- Installation and configuration are separate lifecycle stages.
- Imported content is untrusted data and cannot override JamesOS policy.

## Related tracking issues

- #1 Job Queue foundation
- #2 Documentation, README, and server configuration
- #3 Jade Creative Studio foundation
- #4 Commerce daily product pipeline
- #5 Local ComfyUI setup
- #6 Printify draft integration
- #7 Phone ingestion via Tasker
- #9 Agent OS and one-approval commerce roadmap
- #10 The Agency vertical slice
