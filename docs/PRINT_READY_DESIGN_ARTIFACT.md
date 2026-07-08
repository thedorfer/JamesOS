# Print Ready Design Artifact

JamesOS image jobs now track a `design_artifact` for print artwork that James can review and manually upload later.

Current milestone output is a production candidate, not guaranteed final print-ready art:

- artifact type: `print_ready_png`
- target print size: `4500x5400`
- source generation size: usually `1024x1024`
- background: transparent requested
- transparency method: `prompt_only`
- background removal required: true
- upscale required: true
- provider target: `printify`

## Source vs Final Size

The GTX 1080 Ti may not reliably generate `4500x5400` directly. JamesOS therefore creates smaller source artwork first, saves it locally, and marks whether upscale is still required.

Generated files are saved under:

```text
~/JamesOSData/JamesOS/CreativeStudio/Generated/YYYY-MM-DD/JOB_ID/
```

## Transparency

The managed transparent workflow uses only built-in ComfyUI nodes. Basic ComfyUI generation does not create true alpha transparency by itself, so JamesOS marks:

```text
transparent_background_requested: true
transparency_method: prompt_only
background_removal_required: true
```

No external background-removal services are called.

## Manual Printify Upload

JamesOS does not call Printify. When a PNG exists, the job is marked for POD review/manual upload, but provider writes remain disabled.

Future phases may add local background removal and upscaling workflows before marking an artifact `final_print_ready`.

## Design Quality

Production candidates are driven by `design_recipe`, then transformed into structured prompt sections:

- `STYLE`
- `SUBJECT`
- `TYPOGRAPHY`
- `LAYOUT`
- `PRINT`

Recipe templates include typography, sticker, minimal, vintage, retro, badge, emblem, line art, cartoon, grunge, watercolor, and seasonal. `premium` quality adds vector-like edges, crisp typography, balanced spacing, isolated artwork, transparent background, high contrast, and thumbnail optimization.

Assets remain metadata-only. Filenames are translated into semantic descriptions such as “six-stripe rainbow pride flag colors” before prompt building.
