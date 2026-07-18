# The Marine (planned)

Last reviewed: 2026-07-18

The canonical easter-egg agent name is **The Marine**. It may eventually be discovered through JamesOS chat or an optional hidden IDDQD-style trigger and open the registered `marine.play` workspace.

The game runs in a sandboxed browser component using open or user-provided assets. Proprietary game assets must not be committed. It has no terminal, filesystem, provider, agent-tool, network, or privilege capability. It pauses while hidden and provides Close and Fullscreen controls.

Acceptance requires tests for chat invocation, bounded view registration, sandbox attributes, no network or privileged access, pause/resume, close/fullscreen, and asset-policy enforcement.
