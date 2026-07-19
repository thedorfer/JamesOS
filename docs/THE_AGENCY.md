# The Agency

Last reviewed: 2026-07-19

The Agency is the implemented agent-management workspace in `/app`. It provides My Agents, Marketplace, Runs, Approvals, Updates, agent detail, permission review, protected lifecycle actions, private mutable registry state, and sanitized auditing.

Installation, enablement, and execution are separate states. An installed and enabled agent is normally `idle` until a run starts. Other states include running, waiting for approval, degraded, blocked, and update available.

## Installed agents

- **Jade:** core, enabled, idle when not running, protected from removal
- **The Merchant:** installed, enabled, idle when not running, associated with Product Studio
- **The Administrator:** installed, enabled, idle when not running, associated with Admin; limited to registered operations and granted no arbitrary file writing, shell, terminal, environment, or network authority

## Marketplace

The Archivist, The Mechanic, and The Scribe are planned catalog entries. They are displayed as future curated options and are not installable implementations. Remote marketplace distribution, package verification, updates, and rollback remain planned.

Agents may provide bounded text, registered navigation suggestions, validated local form patches, diagnostics, and confirmation requests. They cannot supply executable UI, remove locked anchors, overwrite protected layouts, bypass access policy, contact providers outside declared operations, approve their own protected actions, publish, or order.

Optional agents may be disabled or removed only under their declared lifecycle. Protected core agents and Jade/system locks remain authoritative.

[The Marine](THE_MARINE.md) remains a planned capability-free sandboxed game workspace.
