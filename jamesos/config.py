from pathlib import Path

# Human-facing notes vault. Keep this clean for Obsidian/manual notes.
NOTES = Path.home() / "Notes"
NOTES_VAULT = NOTES.resolve()

# Machine-owned JamesOS data. Archives, queues, imports, generated reports,
# indexes, databases, and extracted brain data live here instead of cluttering Notes.
JAMESOS_DATA = (Path.home() / "JamesOSData").resolve()

# Backward-compatible alias used throughout existing services.
# New code should prefer JAMESOS_DATA for system storage and NOTES_VAULT for
# human-facing notes.
VAULT = JAMESOS_DATA
