# Installing JamesOS Agents

Installation and configuration are separate lifecycle stages in JamesOS.

- **Install / Hire** makes an agent available in **Your Team**.
- **Configure** supplies non-secret settings, permission grants, and secret-handle grants.
- **Enable / On Duty** is allowed only after required setup is complete.

## Current installation model

The first Agency milestone uses checked-in manifests under:

```text
agency/manifests/
```

`DirectoryCatalogProvider` reads these manifests locally. It does not download packages, run installers, modify repositories, or execute third-party code.

A built-in agent becomes available after its code, manifest, registration, and tests are present in the JamesOS checkout.

## Install JamesOS itself

From a trusted checkout:

```bash
git clone https://github.com/thedorfer/JamesOS.git
cd JamesOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover tests
```

Flutter/Jade setup is documented separately in the desktop setup and project README.

## Hire an available agent in Jade

1. Open Jade.
2. Open **The Agency**.
3. Select **Discover**.
4. Open the agent details.
5. Review the publisher, version, capabilities, permissions, configuration, secrets, platform support, and installation metadata.
6. Select **Hire** and confirm.
7. Complete configuration before placing the agent **On Duty**.

Hiring persists local state under:

```text
~/JamesOSData/JamesOS/Agency/
```

## Hire through the local API

Use normal JamesOS API authentication:

```text
GET  /agency/catalog
GET  /agency/agents/{agent_id}
POST /agency/agents/{agent_id}/hire
```

Mutations preview by default. A confirmed request is required to change state.

Example request body:

```json
{
  "confirmed": true
}
```

## Installation-provider boundary

Future package providers must implement a separate, approval-gated installation boundary. A catalog provider may describe a package but may not install it.

A future installer must verify at minimum:

- manifest identity and version
- supported JamesOS version
- operating system, distribution, and architecture
- publisher and package provenance
- package checksum or signature
- requested permissions and side effects
- install plan before execution
- explicit user confirmation
- post-install registration and health
- rollback or release behavior

Potential providers include:

- built-in checkout content
- a read-only GitHub catalog plus reviewed source/package retrieval
- a separately approved Debian/APT package provider

Discovery alone must never execute code.

## Updating an agent

Update support is a future lifecycle operation. It should follow:

```text
Discover update
→ inspect version and permissions changes
→ preview install plan
→ confirm
→ install once
→ verify
→ retain rollback evidence
```

An update that adds permissions, secrets, side effects, or protected-resource access requires fresh review.

## Releasing an agent

Release removes the hired-agent lifecycle record only after explicit confirmation. Secret values remain controlled by the secret provider; grants should be revoked. A future package provider may separately offer an uninstall plan.

## Safety rules

- Install only from a reviewed source.
- Never paste credentials into a manifest or ordinary configuration field.
- Never bypass manifest compatibility checks.
- Never allow a catalog parser to execute package commands.
- Never run unattended package installation.
- Keep private deployment state outside Git.

## Related guides

- [Building agents](BUILDING_AGENTS.md)
- [Configuring agents](CONFIGURING_AGENTS.md)
- [Submitting agents](AGENT_SUBMISSIONS.md)
- [The Agency](THE_AGENCY.md)
