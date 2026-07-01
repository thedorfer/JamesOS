# JamesOS Responsibility Split

JamesOS is split into deterministic Python services and AI-assisted reasoning.

## Python Services

Python should handle anything that must be reliable, repeatable, and testable.

Examples:
- Create notes
- Move notes
- Rename notes
- Refresh dashboards
- Start day workflow
- End day workflow
- Capture inbox notes
- Scan vault content
- Extract known entities
- Build JSON indexes
- Update knowledge notes
- Sync backups
- Maintain folder structure

Python should not guess intent unless rules are clear.

## AI Layer

AI should handle ambiguity, interpretation, summarization, and suggestions.

Examples:
- Summarize messy brain dumps
- Classify unclear inbox captures
- Suggest which ticket a note belongs to
- Draft communication
- Explain relationships
- Prioritize daily work
- Detect likely follow-up actions
- Help write ticket updates
- Create natural language summaries

AI should suggest actions before modifying important notes unless the action is obvious.

## Rule of Thumb

If it can be expressed as a deterministic rule, Python does it.

If it requires judgment, context, tone, or ambiguity resolution, AI does it.

## Data Flow

```text
Raw input
  ↓
Inbox capture
  ↓
Python entity scan
  ↓
Knowledge index
  ↓
AI suggestions
  ↓
Approved actions
  ↓
Obsidian updates
```

## Source of Truth

Obsidian Markdown files are the human-readable source of truth.

JSON indexes are machine-readable support files.

AI outputs are advisory unless explicitly approved.
