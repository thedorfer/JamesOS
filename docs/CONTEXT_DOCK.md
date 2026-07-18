# Context Dock

Last reviewed: 2026-07-18

The Context Dock is primary application navigation. Home, The Agency, and Admin are permanent system-locked anchors. Deterministic context slots may show the active workspace, current job, review, diagnostics, recent workspaces, or validated agent suggestions.

Badges represent progress, ready, warning, and pending approval. Recalculation occurs after meaningful state transitions, not continuously, and never reorders items during pointer interaction. Agent suggestions cannot remove, replace, or reorder locked anchors or introduce unknown views.

During generation the current job is available; review replaces it when ready; diagnostics appears on failure. Home remains reachable in every state.
