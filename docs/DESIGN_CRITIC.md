# Design Critic

Design Critic evaluates a planned or generated design using metadata only.

It does not use vision or OCR yet. Current critique uses design plans, recipes, prompt metadata, artifact metadata, layer manifests, and known product constraints.

Storage:

```text
~/JamesOSData/JamesOS/CreativeStudio/Critiques/YYYY-MM-DD/
```

API:

```text
GET /design-critic/health
POST /design-critic/critique-plan
POST /design-critic/critique-artifact
GET /design-critic/critiques/{critic_id}
```

CLI:

```bash
python3 scripts/critique_design_plan.py PATH_TO_DESIGN_PLAN_JSON
python3 scripts/critique_design_plan.py PATH_TO_DESIGN_PLAN_JSON --save
```

Critique dimensions:

- print readiness
- product fit
- commercial consistency
- recipe adherence
- composition
- typography
- transparency
- layer reuse

Product-aware rules:

- underwear rewards no-text/minimal text, repeat patterns, balanced motif spacing, and wearable scale
- underwear penalizes slogans and large typography
- shirts, mugs, stickers, totes, and hoodies reward readable text when the recipe expects typography
- all products penalize positive mockup/person/lifestyle/photo language
- all products need transparency and resolution metadata for high print readiness

Safety:

- no Printify calls
- no InkedJoy calls
- no Etsy calls
- no upload, publish, order, or send
- provider writes remain false
