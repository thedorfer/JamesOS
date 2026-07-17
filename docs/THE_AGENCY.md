# The Agency

The Agency is JamesOS's local-first interface for discovering and managing agents. Agents are **hired** into **Your Team**, placed **On Duty** after their required setup is complete, moved **Off Duty** without losing configuration, and **released** with explicit confirmation.

## Architecture

Checked-in JSON manifests are read through `CatalogProvider`. The first provider, `DirectoryCatalogProvider`, does no network access and never installs packages. A future GitHub-backed catalog can implement the same read-only provider contract. Package acquisition is deliberately represented only as manifest metadata; a future APT provider belongs behind a separately approved installer boundary and must not execute through catalog parsing.

`AgencyService` coordinates the existing Agent OS concepts:

- versioned `PackageManifest` data remains the runtime registration contract;
- Agency metadata adds category, tags, typed configuration, required/optional permissions, secret references, platform support, and package/media placeholders;
- `AgencyStore` atomically persists hired state under `~/JamesOSData/JamesOS/Agency/state.json` with mode `0600`;
- `AgencySecretProvider` extends the existing handle-based `SecretProvider`. Configuration stores only requirement-to-handle grants, never secret values;
- permissions and lifecycle changes are previewed by default and require `confirmed: true` to mutate state.

The API is rooted at `/agency`. Jade's Discover, Your Team, and management views consume manifest metadata directly. Configuration widgets switch on the declared `string`, `integer`, `boolean`, `enum`, or `url` type; they contain no agent-specific fields.

## Safety and readiness

Hiring, release, enable/disable, configuration, permission grants, and secret grants are confirmation-gated. An agent cannot go On Duty while required configuration, permissions, or secret handles are missing. Secret status responses expose only a handle and configured flag. Activity records contain lifecycle event names and timestamps.

The milestone does not fetch remote catalogs, modify repositories, install APT packages, execute third-party code, publish, purchase, or contact providers.

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

Use the normal JamesOS API authentication. Never put plaintext secrets in configuration requests; create or select a secret handle and grant that handle to the declared requirement.
