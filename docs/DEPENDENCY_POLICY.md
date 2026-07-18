# Dependency policy

Last reviewed: 2026-07-18

- Pin production dependencies deliberately and document compatibility bounds.
- Prioritize security fixes and supported runtimes; triage deprecation warnings before removal deadlines.
- Do not perform blind major-version upgrades.
- Test backend, API, workspace, commerce, and relevant Flutter surfaces proportionally.
- Keep dependency maintenance in separate focused commits with rollback instructions.
- Never combine dependency churn with provider, publication, order, or privilege behavior changes.

Known warnings are tracked as issues with owner, affected dependency, target version, and verification plan.
