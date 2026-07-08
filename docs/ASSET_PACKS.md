# Asset Packs

Asset Pack importer copies reusable folders, zip files, or single assets into machine-owned JamesOS storage:

```text
~/JamesOSData/JamesOS/CreativeStudio/Assets/Packs/
```

Supported categories:

- flags
- hearts
- stars
- flowers
- bows
- sparkles
- animals
- seasonal
- typography_frames
- badges
- patterns
- backgrounds
- icons
- product_safe_patterns

Each imported pack writes `asset_pack_manifest.json` with:

- source
- license
- commercial_allowed
- attribution_required
- notes
- imported_at

Font files are metadata-only in manifests. JamesOS does not expose font file contents or binary asset contents through the API.

## CLI

```bash
python3 scripts/import_asset_pack.py ./my-pack.zip \
  --name pride-motifs \
  --license "Commercial license" \
  --source "local archive" \
  --commercial-allowed \
  --notes "Reusable flags, hearts, and sparkle motifs"
```

Safety boundaries:

- no Printify calls
- no InkedJoy calls
- no Etsy writes
- no upload, publish, order, or send
