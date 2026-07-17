# Contributing to JamesOS

Thank you for your interest in JamesOS.

Issues, bug reports, testing feedback, documentation suggestions, architecture discussions, and agent proposals are welcome.

JamesOS is licensed under the PolyForm Noncommercial License 1.0.0.

Code contributions are not currently accepted for merging unless the contributor has entered into a separate contributor agreement with the project owner. This is necessary to preserve the project owner's ability to use and license JamesOS commercially.

## Proposing an agent

Use the **Agent proposal** issue template before beginning a substantial agent implementation. The proposal should describe capabilities, permissions, secret requirements, side effects, installation, configuration, storage, approval behavior, recovery, and tests.

Developer path:

1. Read [Building Agents](docs/BUILDING_AGENTS.md).
2. Define a versioned Agency manifest.
3. Keep installation and configuration as separate lifecycle stages.
4. Add runtime registration, tests, and documentation.
5. Follow [Installing Agents](docs/INSTALLING_AGENTS.md) and [Configuring Agents](docs/CONFIGURING_AGENTS.md).
6. Follow the complete [Agent Submission Process](docs/AGENT_SUBMISSIONS.md).
7. Open a focused pull request only after the contributor-agreement requirement is resolved.

## Private data

Do not include credentials, private deployment information, account IDs, shop names, product IDs, listing IDs, customer data, private artwork, browser cookies, session data, or personal records in issues or pull requests.

Tests must use temporary directories, fixtures, and mocked adapters rather than real `~/JamesOSData` state or external providers.

## Validation

Run:

```bash
git diff --check
python -m unittest discover tests
```

For Jade changes:

```bash
cd apps/jade_app
flutter analyze
flutter test
```

Pull requests should document capabilities, permissions, secret references, side effects, approval gates, installation/configuration changes, tests, external calls, and any remaining work.
