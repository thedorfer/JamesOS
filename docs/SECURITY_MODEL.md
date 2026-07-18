# Security model

Last reviewed: 2026-07-18

- JamesOS is loopback-first. Private remote access may use an SSH tunnel or explicitly configured Tailscale Serve; direct public exposure and Tailscale Funnel are prohibited. LAN mode requires exact hosts, origins, and CIDRs and fails closed when incomplete.
- Mutating browser routes preserve CSRF/same-origin protections and bounded inputs.
- Model output is schema-validated and cannot provide executable UI, shell, selector, URL, or theme content.
- Authority order is Jade/system policy, immutable job bindings, user confirmation, then bounded agent suggestions.
- Provider writes require explicit visible confirmation. Uncertain writes require manual verification, not automatic retry.
- Commerce destination, confirmed provider IDs, publication state, order state, and protected panels cannot be silently changed.
- Credentials and private data stay outside Git beneath `~/JamesOSData`; documentation never includes secret values.
- Terminal and privilege capabilities are planned. There is no approved persistent root shell, stored sudo password, or implicit elevation.

See [Terminal security](TERMINAL_SECURITY.md) and [Commerce workflow](UNIFIED_COMMERCE_WORKFLOW.md).
