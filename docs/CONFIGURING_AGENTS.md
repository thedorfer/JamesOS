# Configuring JamesOS Agents

Configuration happens after an agent is hired and before it is placed On Duty.

JamesOS separates setup into three categories:

1. ordinary non-secret configuration
2. permission grants
3. secret-handle grants

An agent cannot be enabled while required setup is incomplete.

## Ordinary configuration

Manifest-driven fields support:

```text
string
integer
boolean
enum
url
```

Each field may define a label, required flag, default, and enum choices. Values are validated against the manifest before being stored.

Examples:

- result limit
- operating mode
- approved source URL
- feature toggle
- profile reference

Do not use ordinary configuration for credentials, cookies, tokens, private keys, or passwords.

## Permissions

The manifest separates required and optional permissions.

Examples include:

- local read scopes
- local write scopes
- tool-broker permissions
- approved network domains
- declared side effects

Review permission changes literally. An optional permission should remain ungranted until the feature is needed. A newly requested permission during an update requires fresh review.

## Secrets

Secrets are stored through the JamesOS secret provider. The Agency stores only:

- the declared requirement name
- an opaque secret handle
- whether the requirement is configured
- the grant relationship

The secret value is never returned through normal configuration, status, activity, or API responses.

Recommended flow:

```text
Create or select secret
→ receive opaque handle
→ review agent requirement
→ grant handle to requirement
→ verify configured status
```

Never put a plaintext secret in:

- an Agency manifest
- a Git commit
- a normal configuration request
- an issue or pull request
- an activity record
- a screenshot

## Configure in Jade

1. Open **The Agency**.
2. Select **Your Team**.
3. Open the agent.
4. Complete **Configuration** fields.
5. Review and grant **Permissions**.
6. Create/select and grant required **Secrets**.
7. Review readiness.
8. Place the agent **On Duty** only after setup is complete.

## Configure through the API

Use normal JamesOS API authentication:

```text
GET /agency/agents/{agent_id}/configuration
PUT /agency/agents/{agent_id}/configuration
GET /agency/agents/{agent_id}/permissions
PUT /agency/agents/{agent_id}/permissions
GET /agency/agents/{agent_id}/secrets
PUT /agency/agents/{agent_id}/secrets
POST /agency/agents/{agent_id}/enable
```

Mutations preview by default and require explicit confirmation to persist.

## Readiness checks

Before enablement, JamesOS verifies:

- the agent is hired
- the manifest is valid and compatible
- required configuration is present and valid
- required permissions are granted
- required secret handles are granted
- protected resources are not targeted
- the requested capability is declared
- side effects are declared
- retry limits do not exceed policy

Readiness is not permission to perform a consequential action. Each external or privileged operation still follows its own approval gate.

## Private profiles

Deployment-specific settings belong under:

```text
~/JamesOSData/JamesOS/Profiles/
```

Examples include selected commerce policy, protected resources, local resume references, target locations, and other user-specific configuration. Public agent code should consume validated profile data without embedding it in static manifests.

## Changing configuration

A configuration change may invalidate prior approval when it changes the exact target, destination, content, permissions, secret grant, or intended side effect. The agent should return to a reviewable state rather than silently continue.

## Disabling and releasing

- **Off Duty** preserves configuration but prevents normal execution.
- **Release** removes the hired lifecycle record after confirmation.
- Revoke secret grants when they are no longer needed.
- Removing a grant must not reveal or delete the underlying secret unless a separate secret-management action is confirmed.

## Related guides

- [Building agents](BUILDING_AGENTS.md)
- [Installing agents](INSTALLING_AGENTS.md)
- [Submitting agents](AGENT_SUBMISSIONS.md)
- [The Agency](THE_AGENCY.md)
