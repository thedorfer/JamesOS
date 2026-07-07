# Creative Intelligence

Creative Intelligence is a local-first idea, prompt, product-planning, and performance-learning package for JamesOS.

Current foundation:

- local deterministic trend candidates
- niche and idea generation
- prompt draft generation
- product-plan draft generation
- SQLite-backed local records
- read-only Etsy performance history foundation for UnityStitches

It is not an autopublisher. Creative Intelligence does not call InkedJoy, Printify, ComfyUI, or Etsy write APIs in this phase.

Current POD planning decision:

- Printify is the active planned POD provider for MVP shop automation.
- InkedJoy is future/manual-upload only and not active for current automation.
- Bagholder Supply Co and Cheeky Peach Prints both prefer Printify for now.
- Women's underwear, panties, and thongs prefer Printify for now.

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

Prompt formatting is assembled from non-empty parts only. Optional fields do not create leading punctuation or empty phrases such as `Assets/reference motifs: .`.

Product artwork means flat print-ready design artwork by default:

- standalone centered print graphic
- white or transparent-background-friendly background
- high contrast and large readable text
- no person, model, mannequin, hands, face, body, lifestyle room, or product photo
- no mockup unless the creative stage is explicitly `mockup`
- POD-safe and review-only

Creative Spec is the structured bridge from product idea to image plan:

```yaml
creative_spec:
  brand_id:
  brand_name:
  product_type:
  stage:
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
  design_recipe:
    product_type:
    niche:
    design_goal:
    artwork_type:
    background:
    layout:
    palette:
    text:
    typography:
    motifs:
    assets:
    effects:
    provider:
    print_notes:
```

Prompt Library renders `design_recipe` first when present, then falls back to the broader `creative_spec`. It converts the result into a prompt package with positive prompt, negative prompt, width, height, recommended workflow type, and recommended model family. Raw prompt strings still work as fallback.

For `stage: design_art`, Prompt Library recommends `print_design_basic`. `product_art_basic` remains a compatibility alias for older workflows.

Brand assets may be suggested as metadata. Pride/LGBTQ/trans/intersex prompts prefer matching flag assets when present. Binary files are not embedded in prompts, and font file paths are not exposed.

When `performance_history` contains data, scoring can:

- boost niches and product types with real sales
- reward higher conversion patterns
- reduce scores for crowded low-conversion patterns

The scoring layer reads local performance history only. It does not call Etsy directly.
