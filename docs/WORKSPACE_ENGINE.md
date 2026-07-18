# Workspace Engine

Last reviewed: 2026-07-18

`WorkspaceState` binds a conversation to `active_view`, `active_profile_id`, `selected_job_id`, forms, pending confirmations, and reversible activity history.

The server owns a strict view registry, fixed component registry, and command allowlist. Registered components include banners, cards, text, forms, bounded inputs, radio/select choices, tags, progress, galleries, diagnostics, confirmations, and action bars. Commands are limited to navigation, profile selection, form patch/clear, job/review opening, notifications, and confirmations. Unknown commands fail validation.

Agent commands may patch allowed local fields and suggest a view. They cannot submit forms, contact providers, publish, create orders, replace system locks, or write persisted layouts. “Generate it” must produce a visible confirmation; only the user-facing confirmation control may invoke the existing creation route.

Model content may not contain executable HTML, JavaScript, CSS selectors, shell commands, arbitrary URLs, or executable themes. Optional unavailable capabilities must fail locally and visibly without compromising unrelated workspaces.
