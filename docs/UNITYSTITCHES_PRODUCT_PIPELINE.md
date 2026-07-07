# UnityStitches Product Pipeline

UnityStitches is a draft-only daily product package generator for inclusive Etsy/Printify product ideas.

It uses:

```text
Planner -> Job Queue -> Creative Studio pipeline -> local draft package
```

It does not execute ComfyUI, call Printify, call Etsy, publish, order, or send anything.

## Daily Rule

Each run generates exactly two local drafts:

- one `womens_underwear` product
- one rotating configured product from shirt, sweatshirt, hoodie, tote, mug, or seasonal accessory

The rotating product comes from config and is not hardcoded to shirts.

## Config

```text
~/JamesOSData/JamesOS/Config/unitystitches_products.yaml
```

Key safety defaults:

- `create_printify_draft: false`
- `publish_to_etsy: false`
- `send_to_production: false`
- `require_james_approval: true`
- image generation provider is ComfyUI, but execution is disabled

## Storage

Draft packages:

```text
~/JamesOSData/JamesOS/Products/UnityStitches/Drafts/YYYY-MM-DD/
```

Report:

```text
~/JamesOSData/JamesOS/Reports/UnityStitches Product Drafts.md
```

## API

```text
GET /unitystitches/health
POST /unitystitches/generate-daily-drafts
GET /unitystitches/drafts
GET /unitystitches/drafts/{date}
```

## CLI

```bash
python3 scripts/generate_unitystitches_products.py generate
python3 scripts/generate_unitystitches_products.py list
python3 scripts/generate_unitystitches_products.py show-date YYYY-MM-DD
python3 scripts/generate_unitystitches_products.py health
```

## Jade Commands

Supported phrases:

- Generate today's UnityStitches product drafts
- Show UnityStitches drafts needing review

## Draft Contents

Each draft includes product type, niche, product idea, design prompt, negative prompt, Etsy title/tags/description, pricing notes, Printify search notes, `needs_review` status, approval requirement, and false external execution flags.
