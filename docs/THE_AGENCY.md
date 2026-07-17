# The Agency

The Agency is JamesOS's local-first interface for discovering and managing agents. Agents are **hired** into **Your Team**, configured, placed **On Duty** after required setup is complete, moved **Off Duty** without losing configuration, and **released** with explicit confirmation.

Installation and configuration are separate lifecycle stages:

```text
Discover
→ inspect manifest and trust information
→ Hire / install
→ configure non-secret settings
→ grant permissions
→ create or select secret handles
→ grant secret handles
→ verify readiness
→ place On Duty
```

## Architecture

Checked-in JSON manifests are read through `CatalogProvider`. The first provider, `DirectoryCatalogProvider`, does no network access and never installs packages. A future GitHub-backed catalog can implement the same read-only provider contract.

Package acquisition is deliberately represented only as manifest metadata. A future GitHub, Debian, or APT provider belongs behind a separately approved installer boundary and must not execute through catalog parsing.

`AgencyService` coordinates existing Agent OS concepts:

- versioned `PackageManifest` data remains the runtime registration contract;
- Agency metadata adds category, tags, typed configuration, required/optional permissions, secret references, platform support, and package/media placeholders;
- `AgencyStore` atomically persists hired state under `~/JamesOSData/JamesOS/Agency/state.json` with mode `0600`;
- `AgencySecretProvider` extends the existing handle-based `SecretProvider`;
- Agency state stores requirement-to-handle grants, never secret values;
- permissions and lifecycle changes are previewed by default and require explicit confirmation to mutate state.

The API is rooted at `/agency`. Jade's Discover, Your Team, and management views consume manifest metadata directly. Configuration widgets switch on the declared `string`, `integer`, `boolean`, `enum`, or `url` type; they contain no agent-specific fields.

## Lifecycle responsibilities

### Catalog provider

A catalog provider may list and describe agents. It must not install packages or execute code.

### Installer provider

An installer provider acquires and verifies a reviewed package or source. It is a separate future boundary with its own approval, provenance, compatibility, rollback, and verification requirements.

### Configuration

Configuration supplies validated non-secret settings, permissions, and secret-handle grants after installation. Configuration does not itself authorize a consequential action.

### Runtime

The Agent OS resolves capabilities and enforces approval, tool, secret, protected-resource, side-effect, retry, and durable-run policies.

## Safety and readiness

Hiring, release, enable/disable, configuration, permission grants, and secret grants are confirmation-gated. An agent cannot go On Duty while required configuration, permissions, or secret handles are missing.

Secret status responses expose only an opaque handle and configured flag. Activity records contain lifecycle event names and timestamps rather than secret values.

The first milestone does not fetch remote catalogs, modify repositories, install APT packages, execute third-party code, publish, purchase, submit applications, or contact commerce/job providers.

## Local API flow

```text
GET  /agency/catalog
POST /agency/agents/jamesos.example/hire       {"confirmed": true}
PUT  /agency/agents/jamesos.example/configuration
PUT  /agency/agents/jamesos.example/permissions
PUT  /agency/agents/jamesos.example/secrets
POST /agency/agents/jamesos.example/enable     {"confirmed": true}
GET  /agency/agents/jamesos.example/activity
POST /agency/agents/jamesos.example/disable    {"confirmed": true}
POST /agency/agents/jamesos.example/release    {"confirmed": true}
```

Use normal JamesOS API authentication. Never put plaintext secrets in configuration requests; create or select a secret handle and grant that handle to the declared requirement.

## Developer and operator guides

- [Building agents](BUILDING_AGENTS.md)
- [Installing agents](INSTALLING_AGENTS.md)
- [Configuring agents](CONFIGURING_AGENTS.md)
- [Submitting agents](AGENT_SUBMISSIONS.md)
- [Agent OS architecture](AGENT_OS.md)
- [Prioritized roadmap](ROADMAP.md)
