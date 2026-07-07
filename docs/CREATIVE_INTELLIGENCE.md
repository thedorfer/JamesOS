# Creative Intelligence

Creative Intelligence is a local-first idea, prompt, product-planning, and performance-learning package for JamesOS.

Current foundation:

- local deterministic trend candidates
- niche and idea generation
- prompt draft generation
- product-plan draft generation
- SQLite-backed local records
- read-only Etsy performance history foundation for UnityStitches

It is not an autopublisher. Creative Intelligence does not call Printify, ComfyUI, or Etsy write APIs in this phase.

## Etsy Read-Only Performance

The Etsy connector foundation is read-only and exists so future scoring can learn from real UnityStitches performance history.

Safety defaults:

- `readonly: true`
- `writes_enabled: false`
- `publishing_enabled: false`
- `order_fulfillment_enabled: false`

See [Etsy Read-Only Performance History](ETSY_READONLY_PERFORMANCE.md).

## Scoring

Scoring works without Etsy data using local placeholder heuristics.

Compatibility rules run before scoring. Incompatible product/niche combinations are blocked, not merely scored lower.

Hard shop rule:

- teacher, school staff, classroom, education, GCU, kids, student, back-to-school, special education, speech therapy, occupational therapy, and child-related niches must never pair with women's underwear, panties, thongs, lingerie, or intimate apparel

Underwear-safe niches include:

- LGBTQ+ pride
- trans pride
- nonbinary pride
- ally/supporter
- self-love and confidence
- body positivity
- mental health positivity
- be yourself affirmation
- mom pride / family pride
- Thai/English identity
- custom pronoun/name
- holiday pride
- seasonal inclusive
- Valentines love-is-love
- Pride Month
- clean, non-explicit adult spouse/partner humor

Teacher/school niches may pair with non-intimate products such as shirts, sweatshirts, hoodies, totes, mugs, stickers, classroom accessories, and seasonal gifts.

Creative packages include:

- `brand_id`
- `brand_name`
- `brand_voice`
- `brand_compatibility_status`
- `brand_compatibility_reason`
- `compatibility_status`
- `compatibility_reason`
- `blocked_terms`

Brand-specific compatibility is read from the JamesOS Brand Registry first. Local Creative Intelligence rules remain as a fallback safety net.

Phase C adds Prompt Library, Asset Library, and Style Registry support. Image plans may include selected prompt templates, selected style, brand voice, and asset suggestions, while keeping execution disabled.

Creative Spec is the structured bridge from product idea to image plan:

```yaml
creative_spec:
  brand_id:
  brand_name:
  product_type:
  niche:
  audience:
  emotional_hook:
  style:
  colors:
  text:
  typography:
  assets:
  layout:
  print_requirements:
  safety_notes:
```

Prompt Library converts `creative_spec` into a prompt package with positive prompt, negative prompt, width, height, recommended workflow type, and recommended model family. Raw prompt strings still work as fallback.

When `performance_history` contains data, scoring can:

- boost niches and product types with real sales
- reward higher conversion patterns
- reduce scores for crowded low-conversion patterns

The scoring layer reads local performance history only. It does not call Etsy directly.
