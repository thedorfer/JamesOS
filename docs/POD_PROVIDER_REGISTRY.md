# POD Provider Registry

JamesOS uses POD Provider Registry to keep Printify, InkedJoy, and future provider settings out of hardcoded product logic.

Registry path:

```text
~/JamesOSData/JamesOS/POD/pod_provider_registry.yaml
```

Default providers:

- `printify`
- `inkedjoy`

Current safety boundary:

- read-only foundation only
- no InkedJoy calls
- no Printify calls
- no uploads
- no draft creation
- no orders
- no publishing
- no listing creation

Every provider record forces:

```yaml
readonly: true
writes_enabled: false
draft_creation_enabled: false
order_enabled: false
```

## InkedJoy

InkedJoy is enabled as a configurable POD target for UnityStitches, especially for:

- `womens_underwear`
- `panties`
- `thong`
- shirts, hoodies, mugs, totes, and accessories as future configurable products

Status:

```text
API access not confirmed; manual upload/draft-ready mode only.
```

## API

```text
GET /pod-providers
GET /pod-providers/health
GET /pod-providers/{provider_id}
```

These routes read local registry config only. They do not contact external POD services.
