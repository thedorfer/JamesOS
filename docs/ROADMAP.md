# Roadmap

Last reviewed: 2026-07-18

Status is evidence-based: branch implementation is not completion until accepted and promoted to master.

1. **Recovery branch acceptance and promotion** — verify `/app`, service startup, safety locks, and commerce recovery on the desktop; promote with rollback evidence.
2. **Web-first shell** — accept the persistent chat/right-workspace interface and replace remaining legacy entry-point assumptions.
3. **Workspace Engine** — expand deterministic views, reversible state, confirmations, diagnostics, and event lifecycle.
4. **Context Dock** — accept locked anchors and badges; later add bounded registered suggestions without interaction-time reorder.
5. **Layout Manager and themes** — accept persistence and locks; add validated token-only theme packs.
6. **The Agency** — build active agents, runs, assignments, approvals, results, tools, and Jade safety decisions.
7. **Admin and service management** — add profiles, service health/restart controls, layouts, themes, permissions, diagnostics, and dependencies.
8. **Terminal and privilege broker** — add a user-level PTY, exact-command approvals, audit records, and a separately designed restricted Polkit/broker path. Never store a sudo password or provide a persistent root shell.
9. **The Marine** — add the planned `marine.play` sandbox with open/user assets, no network or privileged capabilities, and pause/close/fullscreen controls.
10. **Commerce reliability** — complete end-to-end acceptance for both profiles, immutable destinations, draft recovery, revision, and explicit publication.
11. **Dependency modernization** — triage deprecations and security updates with pinned, isolated maintenance changes and full compatibility tests.
12. **Android/Jade clients** — define a secondary-client API after the web protocol stabilizes; desktop remains the execution host.

Track actionable work in GitHub issues and keep [Current status](CURRENT_STATUS.md) aligned.
