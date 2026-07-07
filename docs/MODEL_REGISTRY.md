# Model Registry

The Model Registry records local model and workflow readiness for future image generation.

Config path:

```text
~/JamesOSData/JamesOS/AI/model_registry.yaml
```

Default model placeholders:

- `sdxl_base`
- `sdxl_typography`
- `flux_schnell`
- `flux_dev`
- `transparent_png`
- `mockup_model`

Every model starts with `status: missing` and `enabled: false`.

Default workflow placeholders:

- `product_art`
- `typography_design`
- `transparent_png`
- `mockup`
- `listing_image`

Every workflow starts with `status: missing` and `enabled: false`.

The registry is read by the Workflow Manager and Image Worker. It does not execute models or workflows.

