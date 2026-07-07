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

- `unitystitches` — enabled default brand for inclusive Etsy/POD apparel and gifts
- `bagholder_supply_co` — enabled foundation profile for Bagholder Supply Co market-chaos shirts
- `cheeky_peach_prints` — enabled foundation profile for Cheeky Peach Prints playful seasonal underwear
- `degen_market_chaos` — disabled placeholder for future market-chaos/meme products

The registry stores brand voice, allowed niches, blocked niches, product lists, blocked product/niche pairs, product mix, preferred POD provider, provider rules, design preferences, SEO preferences, pricing/mockup preferences, trademark notes, approval rules, and integration safety flags.

UnityStitches defaults:

- preferred POD provider: `printify`
- fallback POD provider: `inkedjoy_manual_future`
- women's underwear, panties, and thongs prefer Printify for now

Bagholder Supply Co defaults:

- preferred POD provider: `printify`
- niche: `market_chaos_degen_tshirts`
- product focus: shirts
- daily design target: 3 to 5
- stage default: `print_design_basic`

Cheeky Peach Prints defaults:

- preferred POD provider: `printify`
- fallback POD provider: `inkedjoy_manual_future`
- niche: `womens_underwear_playful_seasonal`
- product focus: women's underwear, panties, and thongs
- daily design target: 3 to 5
- stage default: `print_design_basic`

Image Worker and Creative Intelligence use brand ID, brand name, and brand voice from this registry when preparing local creative plans.

## Safety

All default brands require approval for external actions.

Current defaults:

- Etsy writes disabled
- InkedJoy/Printify provider writes disabled
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
