## Summary

Describe the focused change and the issue it closes or advances.

## Architecture

Explain how this uses existing JamesOS services, Agent OS, Agency, approval, secret, profile, storage, and UI boundaries.

## Capabilities and behavior

- Capabilities added or changed:
- Inputs and outputs:
- Local writes:
- Network reads:
- External writes:
- Supported side effects:
- Retry behavior:

## Permissions and secrets

- Required permissions:
- Optional permissions:
- Secret requirement names:
- Protected resources:

Do not include secret values or private deployment identifiers.

## Installation and configuration

- Installation/provider changes:
- Supported platforms:
- Configuration fields:
- Migration or rollback behavior:

## Safety and privacy

- Approval gates:
- Dry-run behavior:
- Prompt-injection handling:
- Redaction:
- Private-data boundaries:
- Failure and recovery behavior:

## Validation

- [ ] `git diff --check`
- [ ] `python -m unittest discover tests`
- [ ] `flutter analyze` when Jade changes
- [ ] `flutter test` when Jade changes
- [ ] No unintended external calls
- [ ] Tests use temporary data rather than real `~/JamesOSData`
- [ ] No credentials or private deployment data committed

## Evidence

Include test totals, screenshots for UI changes, and any mocked/fixture workflow used for validation.

## Remaining work

List intentionally deferred work and known limitations.

## Contributor agreement

- [ ] A contributor agreement is on file or this pull request is maintained by the project owner.
