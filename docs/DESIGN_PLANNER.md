# Design Planner

Design Planner converts a recipe, Design DNA, product type, brand, and niche into a concrete `design_plan`.

The plan is more specific than a recipe and less model-specific than a prompt. Prompt generation still supports the existing `design_recipe` flow; Design Planner is a foundation for making future prompt generation more consistent.

Storage:

```text
~/JamesOSData/JamesOS/CreativeStudio/DesignPlans/YYYY-MM-DD/
```

API:

```text
GET /design-planner/health
POST /design-planner/plan
GET /design-planner/plans/{plan_id}
```

CLI:

```bash
python3 scripts/create_design_plan.py \
  --brand unitystitches \
  --product womens_underwear \
  --niche "trans pride" \
  --recipe underwear/pride_pattern
```

Product-aware defaults:

- underwear, panties, and thongs use no-text or minimal-hidden-text plans, repeating motifs, wearable scale, and moderate coverage
- shirts, hoodies, totes, mugs, and stickers can use readable typography when the recipe supports it

Safety:

- no Printify calls
- no InkedJoy calls
- no Etsy calls
- no upload, publish, order, or send
- provider writes remain false
