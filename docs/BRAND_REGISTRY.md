# Brand Registry

The Brand Registry centralizes shop/brand rules for JamesOS creative commerce.

Config:

```text
~/JamesOSData/JamesOS/Brands/brand_registry.yaml
```

Report:

```text
~/JamesOSData/JamesOS/Reports/Brand Registry.md
```

Default brands:

- `unitystitches` — enabled default brand for inclusive Etsy/Printify apparel and gifts
- `degen_market_chaos` — disabled placeholder for future market-chaos/meme products

The registry stores brand voice, allowed niches, blocked niches, product lists, blocked product/niche pairs, product mix, design preferences, SEO preferences, pricing/mockup preferences, trademark notes, approval rules, and integration safety flags.

Image Worker and Creative Intelligence use brand ID, brand name, and brand voice from this registry when preparing local creative plans.

## Safety

All default brands require approval for external actions.

Current defaults:

- Etsy writes disabled
- Printify writes disabled
- ComfyUI execution disabled
- no publishing
- no uploading
- no ordering
- no sending

## API

```text
GET /brands
GET /brands/health
GET /brands/default
GET /brands/{brand_id}
POST /brands/{brand_id}/validate
```

Validation checks product/niche compatibility for the selected brand. UnityStitches blocks teacher, school, classroom, education, GCU, kids, student, back-to-school, special education, speech therapy, occupational therapy, and child-related niches from pairing with women's underwear, panties, thongs, lingerie, or intimate apparel.
