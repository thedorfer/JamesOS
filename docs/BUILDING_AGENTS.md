# Building JamesOS Agents

This guide is the starting point for developers who want to build an agent for JamesOS.

An agent is a bounded software component with declared capabilities, permissions, secret requirements, supported side effects, and retry limits. It is not an unrestricted chatbot and it does not receive authority merely because it is installed.

## 1. Choose a stable identity

Use a stable, namespaced agent ID such as:

```text
publisher.agent-name
```

Do not use a private shop, employer, account, customer, or deployment name in public agent code.

## 2. Define the runtime agent

Agents implement the existing Agent OS protocol. A minimal local agent follows this shape:

```python
from jamesos.core.agents.models import (
    AgentExecutionResult,
    AgentManifest,
    AgentPlan,
    AgentStep,
    RiskLevel,
)
from jamesos.core.agents.protocol import AgentDefaults


class ExampleAgent(AgentDefaults):
    manifest = AgentManifest(
        "example",
        "ExampleAgent",
        "0.1.0",
        "Performs a small local task",
        ("example.local_summary",),
        accepted_task_types=("example_work",),
        emitted_result_types=("example_result",),
        required_tool_permissions=(),
        required_secret_handles=(),
        supported_side_effects=(),
        maximum_automatic_attempts=1,
    )

    def plan(self, request):
        return AgentPlan(
            request.task_id,
            self.manifest.agent_id,
            [AgentStep("example", request.requested_capability, "Prepare local work", RiskLevel.READ)],
            {"request": request},
        )

    def execute(self, plan, context):
        return AgentExecutionResult(
            "completed",
            {"result": "example_complete", "write_performed": False},
        )
```

Keep `plan`, `execute`, `verify`, and optional learning behavior deterministic and testable. Never perform undeclared side effects.

## 3. Declare capabilities precisely

Capabilities should describe bounded operations:

```text
career.jobs.rank
commerce.product.read
home.inventory.read
```

Avoid vague capabilities such as `do_everything`. The `AgentRegistry` routes requests by capability, and the `AgentRunner` enforces declared permissions, side effects, approval rules, retry limits, protected resources, and durable run records.

## 4. Add an Agency manifest

Add a JSON manifest under `agency/manifests/`. Start from `agency/manifests/example-agent.json`.

The manifest declares:

- runtime agent metadata and entry point
- category and tags
- capabilities and task/result types
- required and optional permissions
- typed non-secret configuration
- secret requirements as references only
- supported platforms and architectures
- installation-provider metadata
- icon and screenshot metadata

Supported configuration field types are:

```text
string
integer
boolean
enum
url
```

Secret requirements may contain a name, label, and required flag. They may never contain a secret value.

## 5. Separate configuration from secrets

Ordinary configuration can contain non-sensitive values such as limits, modes, URLs, and feature flags. Credentials belong in the JamesOS secret provider. Agency state stores only opaque secret handles and grants.

Never commit:

- API keys or passwords
- browser cookies or sessions
- private profile contents
- account, shop, product, listing, or customer identifiers
- personal data or private artwork

## 6. Register discovery

Built-in agents are exported from `jamesos/agents/__init__.py` and registered through the existing discovery path. Third-party catalog entries must not become executable merely because a manifest was discovered. Installation and runtime registration remain separate, approval-gated steps.

## 7. Add tests

At minimum, test:

- manifest validation
- capability resolution
- dry-run behavior
- approval requirements
- declared side-effect enforcement
- missing configuration, permission, and secret readiness
- protected-resource blocking
- redaction
- maximum one automatic attempt
- no external calls in unit tests

Run:

```bash
python -m unittest discover tests
cd apps/jade_app
flutter analyze
flutter test
```

## 8. Document the agent

Document its purpose, capabilities, inputs, outputs, permissions, secrets, configuration, side effects, limitations, installation method, recovery behavior, and test commands.

## Next guides

- [Installing agents](INSTALLING_AGENTS.md)
- [Configuring agents](CONFIGURING_AGENTS.md)
- [Submitting agents](AGENT_SUBMISSIONS.md)
- [The Agency](THE_AGENCY.md)
- [Agent OS](AGENT_OS.md)
