# Web application

Last reviewed: 2026-07-19

`/app` is the primary JamesOS interface. Legacy commerce entry points redirect to `/app?view=commerce.new`.

The shell keeps Jade chat mounted beside a contextual workspace. Home, The Agency, and Admin are permanent anchors; Product Studio, commerce loading/review/diagnostics, jobs, and agent details appear contextually. Narrow screens use a chat drawer. Health, attachment processing, and layout controls remain same-origin.

Chat travels browser → FastAPI → desktop Ollama (`mistral:instruct`). The browser never contacts Ollama, ComfyUI, Printify, or Etsy directly. The server validates structured commands and treats ordinary prose as text. Model HTML is inert. Enter sends, Shift+Enter inserts a newline, Upload adds conversation-bound attachments, and Clear starts a new conversation.

Private chat is ephemeral and does not persist transcripts, memory, recents, or a conversation ID. Adult mode is implemented behind installation availability, Private chat, and current-session affirmation, but manual acceptance is blocked by a UI/policy-state defect.

Jade may navigate through validated commands and patch allowlisted empty Product Studio fields. It cannot automatically generate, publish, order, change credentials, or broaden permissions. Known defects include noisy model advisories, occasional ordinary-prompt commerce misclassification, and imperfect exact-answer behavior.

The latest real Product Studio browser run failed before an eligible candidate was available. Automated typography and fake-provider tests pass, but the real unpublished-draft path is not validated. See [Current status](CURRENT_STATUS.md).

See [Workspace Engine](WORKSPACE_ENGINE.md), [Context Dock](CONTEXT_DOCK.md), and [Layout Manager](LAYOUT_MANAGER.md).
