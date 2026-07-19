# Unified commerce workflow

Last reviewed: 2026-07-19

Product Studio is the preferred commerce interface at `/app?view=commerce.new`. Bagholder Supply Co. (`bagholder-supply`) and UnityStitches (`unitystitches`) are enabled profile-bound destinations. A destination becomes immutable when a job is created.

The form keeps Exact phrase, Listing title, Product brief, and Special instructions separate. New Listing title starts blank. Multiline phrases are preserved, artwork colors remain separate from garment colors, and profile changes preserve manual edits. Jade may propose validated patches but cannot start generation.

## Implemented and test-covered

- semantic form preflight and immutable destination binding
- deterministic local typography renderer producing three transparent 4500 × 5400 PNG candidates in automated tests
- candidate format, dimensions, transparency, bounds, clipping, scale, contrast, digest, ownership, and duplicate checks
- private candidate storage and provider-free preflight
- local listing title/description preparation and exactly 13 unique Etsy tags
- guarded Printify upload and one-unpublished-draft adapter paths
- provider-action journals, ownership evidence, digest-based reuse, and fail-closed uncertain results
- in-shell progress, failure diagnostics, local retry, and review routing
- no automatic publication, Etsy listing, or order

The **Generate unpublished draft** form submission is the narrow authorization for local artwork, preflight, one image upload, and one job-owned unpublished Printify draft. Publication remains a separate protected workflow.

## Validation status

Automated local preflight and fake-provider tests pass. They made no real provider call and do not validate a real provider workflow.

The latest manual browser attempt failed after `production_artifact_ready` with zero candidates and rejection `no_output`. No Printify draft or Etsy listing was created, nothing was published, and no order was created. The browser/runtime artifact handoff remains under investigation. See [Current status](CURRENT_STATUS.md).

Retries may reuse a validated candidate, confirmed upload, or owned draft. An uncertain provider result is never retried automatically. No job may switch destinations or claim another job's provider resource.
