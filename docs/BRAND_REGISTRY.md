# Brand Registry

The Brand Registry centralizes shop and brand rules for JamesOS creative commerce.

Config:

```text
~/JamesOSData/JamesOS/Brands/brand_registry.yaml
```

Report:

```text
~/JamesOSData/JamesOS/Reports/Brand Registry.md
```

Public repository code provides the registry schema and validation behavior. Deployment-specific brand names, shop identities, provider accounts, protected resources, pricing rules, and product policies belong in private local configuration outside Git.

The registry stores:

- brand voice
- allowed and blocked niches
- allowed and blocked products
- blocked product/niche pairs
- preferred product mix
- preferred POD provider
- provider rules
- design preferences
- SEO preferences
- pricing and mockup preferences
- trademark notes
- approval rules
- integration safety flags

Image Worker and Creative Intelligence use brand ID, brand name, and brand voice from the private local registry when preparing creative plans.

## Product/Niche Compatibility

Compatibility rules are data-driven. A private brand can block unsafe or inappropriate product/niche combinations without hard-coding its identity into public source code or documentation.

For example, education- or child-related niches can be restricted to non-intimate products, while intimate apparel can be limited to explicitly approved adult-safe niches.

## Safety

All brands require approval for consequential external actions unless a private deployment profile explicitly enables a supported guarded workflow.

Public-safe defaults remain:

- marketplace writes disabled until configured
- provider writes disabled until configured
- local image execution approval-gated
- no hidden publishing
- no automatic uploading
- no ordering
- no sending to production

Secrets and identifying deployment values must never be stored in the public registry schema, reports committed to Git, tests, or examples.

## API

```text
GET /brands
GET /brands/health
GET /brands/default
GET /brands/{brand_id}
POST /brands/{brand_id}/validate
```

Validation checks product/niche compatibility for the selected private brand profile.
