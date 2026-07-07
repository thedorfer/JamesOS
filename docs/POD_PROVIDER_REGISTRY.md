# POD Provider Registry

JamesOS uses POD Provider Registry to keep Printify, InkedJoy, and future provider settings out of hardcoded product logic.

Registry path:

```text
~/JamesOSData/JamesOS/POD/pod_provider_registry.yaml
```

Default providers:

- `printify`
- `inkedjoy`

Current MVP decision:

- Printify is the active planned POD provider for automated shop pipeline work.
- InkedJoy remains available as a future/manual-upload provider foundation only.
- Both providers are read-only in JamesOS right now.

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

## Printify

Printify is the preferred provider for current MVP planning:

- Bagholder Supply Co uses Printify for now.
- Cheeky Peach Prints uses Printify for now.
- UnityStitches underwear/panty/thong provider rules prefer Printify for now.

Status:

```text
Active planned POD provider for MVP automation. Read-only foundation; writes, draft creation, uploads, orders, and publishing remain disabled.
```

Design recipes may include `provider: printify` so prompts and plans know the intended review target. This does not call Printify or enable provider writes.

## InkedJoy

InkedJoy remains a configurable future/manual provider target, especially for possible later underwear products:

- `womens_underwear`
- `panties`
- `thong`
- shirts, hoodies, mugs, totes, and accessories as future configurable products

Status:

```text
Future/manual-upload provider only; API access not confirmed; not active for current automation.
```

## API

```text
GET /pod-providers
GET /pod-providers/health
GET /pod-providers/{provider_id}
```

These routes read local registry config only. They do not contact external POD services.
