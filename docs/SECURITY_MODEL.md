# Security model

Last reviewed: 2026-07-19

- JamesOS is loopback-first. Private remote access may use an SSH tunnel or explicitly configured Tailscale Serve; direct public exposure and Tailscale Funnel are prohibited. LAN mode requires exact hosts, origins, and CIDRs and fails closed when incomplete.
- Mutating browser routes preserve CSRF/same-origin protections and bounded inputs.
- Model output is schema-validated and cannot provide executable UI, shell, selector, URL, or theme content.
- Authority order is Jade/system policy, immutable job bindings, user confirmation, then bounded agent suggestions.
- Browser clients use same-origin JamesOS APIs and never directly contact Ollama, ComfyUI, Printify, or Etsy.
- Product Studio's Generate action authorizes only its bounded unpublished-draft workflow. Publication and ordering remain separately protected; uncertain provider writes require manual verification, not automatic retry.
- Commerce destination, confirmed provider IDs, publication state, order state, and protected panels cannot be silently changed.
- Credentials and private data stay outside Git beneath `~/JamesOSData`; documentation never includes secret values.
- Terminal and privilege capabilities are planned. There is no approved persistent root shell, stored sudo password, or implicit elevation.

Admin configuration mutations require same-origin validation, CSRF, revision checks, allowlisted fields, atomic writes, and sanitized auditing. Secrets are represented only by masked/configured state. EHF and bounded service-log views exclude prompts, attachment contents, credentials, environment values, raw provider responses, and private paths; the browser cannot run `journalctl` or arbitrary commands.

See [Terminal security](TERMINAL_SECURITY.md) and [Commerce workflow](UNIFIED_COMMERCE_WORKFLOW.md).
