# Submitting Agents to JamesOS

JamesOS welcomes agent ideas, bug reports, testing feedback, documentation suggestions, and architecture discussions.

Code cannot currently be merged unless the contributor has entered into a separate contributor agreement with the project owner. This preserves the owner's ability to use and license JamesOS commercially under the project's source-available model.

## Submission path

```text
Open Agent Proposal issue
→ discuss scope and safety
→ confirm contributor agreement path
→ build against the Agent OS and Agency manifest
→ add tests and documentation
→ run the complete validation suite
→ open a focused pull request
→ code, security, privacy, and compatibility review
→ inclusion in the checked-in catalog
```

## 1. Open an Agent Proposal

Use the Agent Proposal issue template. Include:

- proposed stable agent ID
- display name and publisher
- problem solved
- capabilities
- inputs and outputs
- required and optional permissions
- secret requirements
- local and external side effects
- supported platforms
- installation method
- data storage locations
- approval and recovery behavior
- test plan

Do not include credentials, private deployment names, account IDs, customer data, product IDs, listing IDs, private artwork, or personal records.

## 2. Scope review

A proposal should be bounded enough to test and reason about. Reviewers will consider:

- whether the capability already exists
- whether the work belongs in an agent, service, integration, or core runtime
- permission minimization
- private-data boundaries
- prompt-injection exposure
- external side effects
- approval behavior
- retry and recovery behavior
- installation provenance
- compatibility and maintenance cost

## 3. Required deliverables

A complete agent contribution normally includes:

- runtime agent implementation
- Agency manifest
- registration/discovery wiring
- unit tests
- API tests where applicable
- Jade tests where applicable
- agent documentation
- installation instructions
- configuration instructions
- security and privacy notes
- screenshots for new user interfaces

## 4. Validation

Run from the repository root:

```bash
python -m unittest discover tests
```

For Jade changes:

```bash
cd apps/jade_app
flutter analyze
flutter test
```

Also run:

```bash
git diff --check
```

Tests must not contact external providers or modify real `~/JamesOSData` state. Use temporary directories, fixtures, and mocked adapters.

## 5. Pull request boundaries

Keep each pull request focused. The description should state:

- issue closed or advanced
- architecture
- files changed
- capabilities added
- permissions and secret requirements
- side effects
- approval gates
- test results
- external calls made during development
- local private data touched during development
- remaining work

Do not combine unrelated agent, commerce, cleanup, or documentation work in one pull request.

## 6. Catalog inclusion

The initial catalog is checked into `agency/manifests/`. Inclusion means the manifest is discoverable; it does not grant execution authority.

Before an agent is included, its manifest and code must satisfy:

- stable identity and version
- compatible JamesOS version
- supported platform metadata
- reviewed entry point
- least-privilege permissions
- opaque secret references only
- declared side effects
- bounded retry policy
- tests and documentation
- no private deployment data

A future remote catalog will add provenance, signing, package review, and trust metadata. Remote discovery must remain separate from installation and execution.

## 7. Updates to existing agents

An update must clearly identify changes to:

- capabilities
- permissions
- secret requirements
- side effects
- storage
- compatibility
- installation method
- migration behavior

Permission or side-effect expansion requires fresh review.

## Related documents

- [Contributing](../CONTRIBUTING.md)
- [Building agents](BUILDING_AGENTS.md)
- [Installing agents](INSTALLING_AGENTS.md)
- [Configuring agents](CONFIGURING_AGENTS.md)
- [The Agency](THE_AGENCY.md)
