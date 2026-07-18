# POD Provider Registry

Last reviewed: 2026-07-18. Provider credentials may be shared at the integration layer, but each shop destination is profile-specific and each job binds immutably to that profile/shop. Credentials remain outside Git; a bound job cannot switch destinations or reuse another job's provider product.

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
- UnityStitches uses its own configured Printify shop destination.
- Bagholder Supply Co. uses its own configured Printify shop destination.

Status:

```text
Historical foundation status: this registry began read-only. Current commerce code can create or resume a confirmed unpublished Printify draft only through the approval-gated profile-bound workflow. Orders remain outside product generation, and publication requires a separate destination-specific confirmation.
```

Design recipes may include `provider: printify` so prompts and plans know the intended review target. This does not call Printify or enable provider writes.

`provider_target: printify` alone grants no authority. Provider writes occur only through the current commerce workflow with immutable job/profile binding, journal evidence, and confirmation policy; uncertain results require manual verification. Generation does not create an order or automatically publish.

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
