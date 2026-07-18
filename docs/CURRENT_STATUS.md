# Current status

Last reviewed: 2026-07-18

## Git evidence

- Documentation branch: `docs/current-vision-20260718` at `4b723f6` before this documentation pass.
- Recovery implementation branch: `recovery/workspace-engine-20260718` at `4b723f6`.
- `master` and `origin/master`: `b7c6f09`.
- Five commits are implemented above master: workspace shell and commerce hardening, `/app` JavaScript delivery, Layout Manager, Context Dock, and shell-health/profile-selector refinement.
- These commits are **not merged to master**. They await desktop acceptance and promotion.

## Status vocabulary

| Term | Meaning |
| --- | --- |
| Merged | Present on `master` |
| Implemented on branch | Code exists on a feature/recovery branch |
| Desktop verified | Directly exercised on the Linux desktop |
| Awaiting acceptance | Needs operator acceptance before promotion |
| Planned | No complete production implementation was found |

## Implemented on the recovery branch

- Web-first `/app` shell with persistent chat and deterministic workspace views.
- Browser-safe structured commands, Undo, confirmation cards, and server-only Ollama access.
- Context Dock with permanent Home, The Agency, and Admin anchors.
- Twelve-column Layout Manager, resizable split, protected panels, token themes, and private persistence.
- Three-state local health indicator without Printify or Etsy health calls.
- Compact commerce profile selector with immutable job binding and untouched-field behavior.
- Hardened commerce preflight, multiline exact phrases, exactly 13 Etsy tags, draft ownership/recovery, and non-raising background failures.

Focused and full automated tests were reported passing on the recovery work. This is implementation evidence, not desktop acceptance or a release.

## Desktop evidence

- Linux desktop is the intended execution host.
- `loginctl` reports linger enabled for `james`.
- On review, `~/.config/systemd/user/jamesos.service` was absent and `systemctl --user is-active jamesos` reported inactive. Therefore the user service is **not currently verified as installed, enabled, or running** on this checkout date.
- Service installation and `/app` acceptance remain required. No secrets or `runtime.env` contents were inspected.

## Merged to master

Master contains the prior commerce listing-tag, local commerce-assistant, recovery, ownership, preflight, and multiline/background-safety work through `b7c6f09`. Consult Git history for exact patch scope; branch-only shell work must not be represented as merged.

## Planned or incomplete

- Recovery-branch desktop acceptance and promotion.
- Operational Agency and Admin workspaces beyond placeholders.
- User-level terminal, command approval cards, and restricted privilege broker.
- The Marine sandboxed game workspace.
- Additional validated themes, dependency cleanup, and Android/Jade secondary-client API.
- Full commerce end-to-end acceptance with fake adapters first, then separately authorized provider validation.

See the [roadmap](ROADMAP.md) and [service operations](SERVICE_OPERATIONS.md).
