# Admin and EHF

Last reviewed: 2026-07-19

Admin is an implemented `/app` workspace. Its areas are Services, Chat diagnostics, Errors & Diagnostics, Provider credentials, Commerce profiles, Network access, Layouts and appearance, and Adult-mode availability. Opening Admin or reading diagnostics does not contact a provider.

Non-sensitive configured values may be displayed. Sensitive fields expose only masked or configured state, password inputs are blank, and fields are read-only until explicit Edit. Save and other mutations require same-origin validation, CSRF, revision checking, allowlisted fields, atomic writes, rollback where supported, and sanitized audit events. Cancel discards the edit.

EHF—Error Handling Framework—is the authoritative error record system. Its sanitized summaries and details include error IDs, severity, operation, stage, job/run links, acknowledgement/resolution state, filters, safe rejection guidance, and related-job navigation. Sanitized export is supported. EHF cannot execute arbitrary commands.

The browser receives only bounded, sanitized service-log data from the backend; it cannot invoke `journalctl` or read log files. Diagnostic responses exclude credentials, authorization data, cookies, CSRF values, prompts, attachment contents, environment values, raw provider payloads, and private paths.

See [Current status](CURRENT_STATUS.md) for acceptance defects and [Security model](SECURITY_MODEL.md) for authority boundaries.
