# Unified commerce workflow

Last reviewed: 2026-07-18

Bagholder Supply Co. and UnityStitches are enabled profile-bound destinations. The recovery `/app` UI uses a compact selector and locked destination summary. Selecting a profile updates only profile-derived guidance and untouched defaults, records changes in Activity, supports Undo, and never mutates the global selected-profile file. The selector locks after `selected_job_id` exists.

Each job persists an immutable profile, Printify shop, Etsy destination, and provider-write evidence. A confirmed Printify product ID is never recreated. Uncertain or unprovable ownership requires manual verification; recovery uses the existing job-bound draft and shop.

Before image or provider work, preflight rejects placeholders and semantically empty briefs. Intentional multiline exact phrases retain all lines and tokens through prompts, candidate evidence, adherence checks, and review. Garment colors and artwork palette are separate concepts. Listing metadata finalization normalizes and validates exactly 13 unique relevant Etsy tags, using profile fallback tags only when appropriate.

The lifecycle is: validate input, generate candidates, persist candidate-specific adherence/novelty reasons, select/review artwork, create or recover one unpublished draft, retrieve mockups, create a review proposal, revise if requested, and await explicit destination-specific publication confirmation.

Safety guarantees:

- Preflight and local failures happen before provider writes.
- Generation creates an unpublished draft; it does not publish.
- Product generation never creates an order.
- Expected background failures are persisted and do not escape into ASGI.
- Failed jobs are not repurposed for unrelated new products.
- Retry is offered only when provider state is certain; confirmed drafts resume rather than recreate.
- Publication remains a separate explicit confirmation tied to the immutable destination.
