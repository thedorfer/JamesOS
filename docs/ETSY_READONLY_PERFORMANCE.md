# Etsy Read-Only Performance History

Creative Intelligence includes a read-only Etsy connector foundation for learning from the UnityStitches shop later.

This phase is intentionally safe:

- no listing creation
- no listing edits
- no publishing
- no renewals
- no deactivation
- no deletion
- no customer messages
- no order fulfillment
- no Printify calls
- no ComfyUI calls
- no image uploads
- no scraping

The connector is for performance history only: listings, receipts, transactions, and synthesized product-performance rows stored locally in JamesOSData.

## Configuration

Etsy configuration is read from environment variables or service-level secret configuration outside Git:

```text
ETSY_ENABLED=false
ETSY_READONLY=true
ETSY_API_KEY=
ETSY_CLIENT_ID=
ETSY_CLIENT_SECRET=
ETSY_REDIRECT_URI=
ETSY_ACCESS_TOKEN=
ETSY_REFRESH_TOKEN=
ETSY_SHOP_ID=
ETSY_SHOP_NAME=UnityStitches
```

Do not commit tokens, OAuth secrets, API keys, exported credentials, or `.env` files containing Etsy credentials.

## OAuth Required

Live Etsy read access requires Etsy OAuth credentials and a shop ID. Until those are configured, the service returns `not_configured` instead of throwing.

The current implementation is a connector foundation. It creates local tables and safe API shapes, but it does not call Etsy yet.

## Local Storage

Creative Intelligence stores machine-owned Etsy performance data under JamesOSData using SQLite:

```text
~/JamesOSData/JamesOS/CreativeIntelligence/creative_intelligence.db
```

Tables:

- `etsy_sync_runs`
- `etsy_listings`
- `etsy_receipts`
- `etsy_transactions`
- `performance_history`

`performance_history` is the synthesized layer used by scoring and future product decisions.

## API Routes

Every Etsy response includes the safety flags:

```json
{
  "readonly": true,
  "writes_enabled": false,
  "publishing_enabled": false,
  "order_fulfillment_enabled": false
}
```

Routes:

```text
GET /etsy/health
GET /etsy/auth-status
POST /etsy/sync-readonly
GET /etsy/performance
GET /etsy/top-products
GET /etsy/underperforming-products
```

## Future Write Access

Future write access, if ever added, must be approval-first and Job Queue-backed. It should be implemented in a separate explicit phase with clear UI review, dry-run output, and James approval before any Etsy-side mutation.

