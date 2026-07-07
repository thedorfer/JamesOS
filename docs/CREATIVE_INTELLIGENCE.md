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

- `compatibility_status`
- `compatibility_reason`
- `blocked_terms`

When `performance_history` contains data, scoring can:

- boost niches and product types with real sales
- reward higher conversion patterns
- reduce scores for crowded low-conversion patterns

The scoring layer reads local performance history only. It does not call Etsy directly.
