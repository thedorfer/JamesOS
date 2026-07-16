# Design Runs

Design runs create recipe-driven variation sets without auto-executing image generation.

Storage:

```text
~/JamesOSData/JamesOS/CreativeStudio/DesignRuns/YYYY-MM-DD/RUN_ID/
```

Each run contains a recipe snapshot, design DNA, four variation folders, design plans, pre-generation critiques, layer manifests, prompt packages, variation JSON, score summaries, and a winner folder after promotion.

Each variation folder includes:

- `design_plan.json`
- `pre_generation_critique.json`
- `layer_manifest.json`
- `prompt_package.json`
- `variation.json`

API:

```text
POST /design-runs/create
GET /design-runs
GET /design-runs/{run_id}
POST /design-runs/{run_id}/score
POST /design-runs/{run_id}/promote-best
```

Helper:

```bash
python3 scripts/create_design_run.py --brand commerce_shop --product womens_underwear --niche "trans pride" --recipe underwear/pride_pattern --variations 4 --quality premium --provider printify
```

Promotion uses print readiness plus the Design Critic `promotion_recommendation`. No image jobs are auto-executed. No provider APIs are called.
