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

## Product / Niche Compatibility

UnityStitches uses Brand Registry brand ID `unitystitches` and asks Creative Intelligence for compatible product/niche packages before writing drafts.

Important shop rule:

- teacher, school staff, classroom, education, GCU, kids, student, back-to-school, special education, speech therapy, occupational therapy, and child-related niches must never pair with women's underwear, panties, thongs, lingerie, or intimate apparel

If the required product is `womens_underwear`, UnityStitches selects only underwear-safe niches such as LGBTQ+ pride, trans pride, nonbinary pride, ally/supporter, self-love, body positivity, mental health positivity, be yourself affirmation, mom/family pride, Thai/English identity, custom pronoun/name, holiday pride, seasonal inclusive, Valentines love-is-love, Pride Month, or clean adult spouse/partner humor.

If the niche is teacher/school/education related, UnityStitches selects only non-intimate products such as shirts, sweatshirts, hoodies, totes, mugs, stickers, classroom accessories, or seasonal gifts.

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

Each draft includes brand ID/name/voice, product type, niche, product idea, design prompt, negative prompt, Etsy title/tags/description, pricing notes, Printify search notes, brand compatibility status/reason, compatibility status/reason/blocked terms, `needs_review` status, approval requirement, and false external execution flags.
