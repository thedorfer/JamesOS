# Current status

Last updated: 2026-07-19

This is the authoritative status document. Specialized and historical documents defer to it when their claims conflict.

## Revision and acceptance state

- Current implementation branch before this documentation pass: `fix/commerce-end-to-end-20260718`.
- Latest implementation commit: `916f14e` (`fix(commerce): complete local artwork and unpublished draft flow`).
- Documentation branch: `docs/current-state-20260718`.
- Desktop service: installed at `~/.config/systemd/user/jamesos.service`, enabled, and intended to remain active through user lingering.
- `/app`: primary web interface and manually exercised on the desktop.
- Commerce: implementation milestone reached, but real browser end-to-end acceptance **failed**.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| Implemented and test-covered | Code exists and supported automated tests exercise it |
| Manually verified | Direct desktop/browser behavior was observed working |
| Manually verified with defects | The feature ran, but named acceptance defects remain |
| Experimental | Present but not accepted for dependable operation |
| Planned | Design or issue exists; complete implementation does not |
| Not implemented | No supported capability exists |

Fake-provider tests never count as real-provider validation.

## Runtime architecture

The Linux desktop runs JamesOS FastAPI, Ollama, GPU work, ComfyUI/local image services, provider integrations, private `~/JamesOSData`, and the systemd user service. The ThinkBook is a browser, SSH, tunnel, and development client. Changes are developed in Git branches and deliberately deployed to the desktop.

Browser clients use same-origin JamesOS APIs. They never directly contact Ollama, Printify, Etsy, or ComfyUI.

## Web-first shell

Implemented and test-covered:

- `/app` with persistent Jade chat and contextual workspace pane
- Home, The Agency, Admin, Product Studio, diagnostics, loading, and review navigation
- permanent Home, The Agency, and Admin anchors
- compact health indicator
- responsive chat/layout behavior and private layout persistence
- uploads, attachment previews, processing receipts, removal, and cleanup
- same-origin APIs, CSRF on mutations, strict structured-command validation, and inert model HTML

Legacy commerce entry points redirect to `/app?view=commerce.new` and are not the preferred interface.

## Jade chat

Implemented and test-covered: local Ollama through the backend, `mistral:instruct`, ordinary prose and structured commands, Enter to send, Shift+Enter for newline, Upload, Clear, attachment receipts, safe plain-text fallback, workspace grounding, and live sanitized diagnostics.

Manually verified with defects:

- model advisory/warning text is too prominent and noisy
- some ordinary prompts may be misclassified as commerce actions
- exact-answer instruction following still needs refinement in the combined acceptance build

### Private chat

Private chat starts a fresh ephemeral conversation. It writes no transcript, memory, recents entry, personalization, or persistent browser conversation ID. Earlier normal conversations are not deleted. Private pending attachments are removed on successful use, removal, Clear, mode changes, or orphan expiry when unreferenced. EHF/logging may retain sanitized operational metadata, never message or attachment content.

### Adult mode

Adult mode is implemented and test-covered. It requires Private chat, installation availability, and a current-session 18+ affirmation. It resets on reload and Clear and changes conversational scope only—not tool, provider, filesystem, terminal, publication, order, configuration, or access-policy authority.

Manual status: blocked. Adult mode can remain unavailable in the browser after Admin availability is enabled. Its UI also contains excess explanatory text and needs a compact toggle-and-label presentation. Do not treat it as accepted until that policy-state defect is fixed.

## The Agency

The Agency registry is implemented and test-covered with My Agents, Marketplace, Runs, Approvals, Updates, permission review, private mutable registry state, and sanitized auditing.

Book Opportunity Scout `0.1.0` is implemented as a built-in Agent OS and Agency catalog agent. It supports labeled DEMO, MANUAL, and public read-only LIVE research modes with cached/throttled Amazon visibility, public web, trend, and public review adapters. It produces evidence-backed ranked concepts, persists reproducible local reports, and supports confirmed local candidate decisions. Book generation, marketplace access, and publication remain out of scope.

Installed does not mean running. Runtime states distinguish installed, enabled, idle, running, waiting for approval, degraded, blocked, and update available.

- **Jade:** core, enabled, normally idle, protected from removal
- **The Merchant:** installed, enabled, normally idle, associated with Product Studio
- **The Administrator:** installed, enabled, normally idle, associated with Admin; registered operations only and no arbitrary file, shell, terminal, environment, or network capability

The Archivist, The Mechanic, and The Scribe are planned marketplace entries, not installable implementations. Optional installed agents may be disabled or removed only within their declared lifecycle; protected core agents cannot.

## Admin and EHF

Admin implements Services, Chat diagnostics, Errors & Diagnostics, Provider credentials, Commerce profiles, Network access, Layouts and appearance, and Adult-mode availability.

Configuration fields are read-only by default and use explicit Edit, Save, and Cancel. Mutations require same-origin validation, CSRF, revision checking, allowlisted fields, atomic writes, rollback where supported, and sanitized audit events. Secrets are never returned in full; password inputs remain blank and status is masked/configured-only.

EHF—Error Handling Framework—is authoritative. It provides sanitized IDs, severity, code, operation, stage, job/run linkage, acknowledgement/resolution, filters, safe detail, related-job navigation, and sanitized export. The browser has no raw `journalctl`, log-file, or arbitrary-command access. Responses exclude secrets, prompts, attachments, environment values, raw provider payloads, and private paths.

## Commerce profiles

- **Bagholder Supply Co.** — profile `bagholder-supply`, Printify shop title `BagholderSupplyCo`, Printify shop ID `28275232`, Etsy slug `BagholdersSupplyCo`
- **UnityStitches** — profile `unitystitches`, Printify shop ID `9437076`, Etsy slug `UnityStitches`

Credentials remain private. A selected destination becomes immutable when bound to a job.

## Product Studio implementation

Implemented and test-covered:

- profile selection and immutable destination display
- separate exact phrase, Listing title, Product brief, and Special instructions fields
- blank Listing title for new work and preservation of manual edits across profile changes
- multiline phrase preservation and separate garment/artwork colors
- validated Jade form patches without automatic generation
- deterministic local typography artwork, provider-free preflight, local metadata, and exactly 13 Etsy tags
- Printify upload/draft adapter paths with ownership journals and idempotency protections
- in-shell diagnostics/retry, unpublished safeguards, and no-order safeguards
- no automatic publication and no automatic order

### Automated validation at `916f14e`

- three deterministic typography candidates were produced
- candidate dimensions were 4500 × 5400
- output was transparent PNG
- provider-free local preflight passed
- fake-provider unpublished-draft tests passed
- complete discovery passed
- automated validation made no real provider calls

This is implementation evidence, not proof of a successful real provider workflow.

### Latest manual browser acceptance: failed

- last completed stage: `production_artifact_ready`
- Printify draft exists: no
- anything published: no
- order exists: no
- image-generation state: `unavailable_or_no_output`
- candidates: 0; accepted: 0; rejected: 0
- rejection code: `no_output`
- local artwork stage returned no eligible output

The real browser-to-unpublished-Printify-draft workflow is **not validated end to end**. No successful-commerce checkpoint tag was created; `checkpoint-commerce-e2e-20260718` intentionally does not exist. No Printify draft or Etsy listing was created, nothing was published, and no order was created.

Commit `916f14e` is an implementation milestone with a remaining browser/runtime artifact-handoff defect, not a verified real-provider completion.

### Current commerce blocker

The next investigation must reconcile why automated local preflight creates candidates while the browser job reaches `production_artifact_ready` with zero eligible output. Evidence is still needed across:

- browser job versus local-preflight execution path
- phrase classification
- production artifact handoff and conversion
- persisted candidate discovery
- candidate ownership/job binding
- candidate path or digest lookup
- retry/resume behavior
- runtime configuration and desktop private-data differences
- stage-name differences between tests and browser runtime

No single cause should be claimed until traced in the failed runtime job.

## Network access

Supported modes are `loopback`, `tailnet`, and `lan`. Loopback is the default. Trusted hosts, origins, and explicit CIDRs are required; incomplete LAN configuration fails closed. Tailscale Serve is the recommended private-network design. Public exposure and Funnel are not configured. The desktop Tailscale installation/deployment status is currently unverified by repository evidence.

## Home and layouts

Home provides Recent workspaces, Needs attention, Work in progress, Quick actions, and Recent results. Known defect: healthy service-status bullets still appear under Recent workspaces. Healthy status belongs in the health indicator and Admin Services; Home should surface service information only when attention is required.

The layout system implements schema migration, required-panel insertion, obsolete-panel removal, geometry clamping, overlap prevention, minimum sizes, responsive Agency cards, Restore default layout, protected Jade/system panels, and private persistence.

## Attachments

Attachments use conversation-bound private storage, generated storage names, ownership checks, CSRF/origin validation, a 10 MiB limit, bounded extraction, safe processing receipts, pending deletion, orphan cleanup, and Private-chat cleanup. Supported types are plain text, Markdown, JSON, CSV, PDF, PNG, JPEG, and WebP. No private storage path is returned and uploaded content is never executed.

## Planned or not implemented

- browser terminal, restricted PTY, and privilege broker
- The Marine game workspace
- remote/installable Agent marketplace distribution
- installable Archivist, Mechanic, and Scribe packages
- mature agent update/rollback distribution
- broad multi-user authentication beyond trusted private-network access
- generated lifestyle/model garment mockups

Optional lifestyle mockups should preserve approved print artwork using garment templates, masks, and perspective placement. Synthetic adult models/settings may be generated as marketing assets, never as replacement print artwork. Uploaded real-person likenesses require an appropriate consent workflow. Publication remains manual and separately protected.

## Immediate blockers

1. Trace the real browser commerce artifact-handoff failure.
2. Repair Adult-mode availability state in the browser.
3. Reduce Jade warning noise and validate command intent.
4. Remove healthy status bullets from Home Recent workspaces.
5. Verify the intended private-network/Tailscale deployment.
6. Design optional synthetic lifestyle garment mockups without altering source artwork.
