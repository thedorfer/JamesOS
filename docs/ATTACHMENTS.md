# Attachments

Last reviewed: 2026-07-19

Shell attachments use private, conversation-bound storage beneath machine-owned JamesOS data. Storage names are generated; ownership is validated; no private path is returned to the browser. Upload and mutation routes enforce origin/access policy and CSRF. Uploaded content is parsed as data and is never executed.

The upload limit is 10 MiB per file. Supported types are plain text, Markdown, JSON, CSV, PDF, PNG, JPEG, and WebP. Extraction is bounded and validates type/signature where inspection is supported. Executable, script, archive, traversal, unsupported, mismatched, oversized, and unknown attachment inputs fail safely.

Successful processing returns a sanitized receipt. A user-removed pending attachment is deleted when it is not referenced by an active conversation or job. Expired unreferenced orphans are cleaned up. Private-chat attachments are removed after successful use, explicit removal, Clear, mode transition, or orphan expiry as applicable. Cleanup never deletes attachments still referenced by active jobs or conversations.
