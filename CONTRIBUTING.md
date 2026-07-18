# Contributing

Start with [documentation index](docs/INDEX.md), [architecture](docs/ARCHITECTURE.md), and [security model](docs/SECURITY_MODEL.md).

## Evidence and documentation

- Derive status from Git and direct verification. Distinguish merged to master, implemented on a branch, desktop verified, awaiting acceptance, and planned.
- Update user-facing architecture docs in the same change as a visible route, view, navigation, layout, health, approval, or capability change.
- Keep `docs/INDEX.md` canonical, use relative links, preserve labeled history, and do not include secrets, private identifiers, runtime data, or diagnostics.
- Disclose every agent capability, optional dependency, network read, local write, external write, provider operation, terminal requirement, privilege requirement, and failure mode.

## Safety contracts

- External writes require explicit visible confirmation and destination binding. Tests use fake adapters and prove no publication or order unless that exact behavior is under separately authorized test.
- Agent/model output cannot supply executable HTML, JavaScript, CSS selectors, arbitrary URLs, shell commands, or executable themes.
- System/Jade locks override agents, users, and saved layouts. Destination, publication, order, and confirmation controls stay visible and protected.
- Terminal proposals must declare whether they modify state. Privileged work requires a separately reviewed exact-operation broker; never store a sudo password or add a persistent root shell.
- Optional-capability failures must degrade safely without breaking unrelated workspaces.

## Development

Prefer small focused changes and temporary test data. Never write test state to real `~/JamesOSData` or modify private profiles.

```bash
git diff --check
python -m unittest discover -s tests -q
python -m compileall -q jamesos scripts
```

Run Flutter analysis/tests when Jade changes. Include test totals, rollback instructions, documentation updates, and mocked external-call evidence in the pull request.
