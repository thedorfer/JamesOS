# Knowledge Graph Editing Roadmap

Knowledge Graph editing is a future capability. The current implementation exposes edit capability metadata only; it does not edit graph data.

## API

```text
GET /knowledge-graph/edit-capabilities
```

Current response indicates that editing is disabled and lists planned capabilities.

## Planned Capabilities

- edit summary
- add fact
- mark fact wrong
- merge entity
- refresh from evidence
- source citations
- confidence levels

## Safety Model

Future editing should preserve local evidence and citations. JamesOS should distinguish between:

- facts directly supported by evidence
- inferred relationships
- user corrections
- stale or disputed facts

Potential destructive operations, such as merging entities or marking facts wrong, should remain reviewable and reversible.
