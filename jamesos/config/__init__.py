from pathlib import Path

# Human-facing Obsidian notes vault.
NOTES = Path.home() / "Notes"
NOTES_VAULT = NOTES.resolve()

# Machine-owned JamesOS data root.
JAMESOS_DATA = (Path.home() / "JamesOSData").resolve()

# Backward-compatible alias used by existing services.
VAULT = JAMESOS_DATA
