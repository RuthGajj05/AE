# Square inventory

Nearby's `/inventory` screen reads Square catalog variations and `IN_STOCK` counts for one active location at a time. It supports a location picker, product/SKU search, stock filters, local low-stock thresholds, manual refresh, and CSV export. Inventory works independently of the research questionnaire and does not call Claude.

## Connect a sandbox account

1. Create or select an application in the [Square Developer Console](https://developer.squareup.com/apps). Use its Sandbox environment and select a Sandbox test account.
2. Add items and variations in the Sandbox Seller Dashboard. Enable inventory tracking and record stock at an active location. Merely creating an item does not create a known inventory count.
3. Configure the following server environment values. In a private Sites deployment, use the Site's runtime environment settings and store `SQUARE_ACCESS_TOKEN` as a secret. For local development, use an untracked `.dev.vars` file. Never put a token in client code, Git, a URL, or browser storage.

```text
SQUARE_ACCESS_TOKEN=<your sandbox access token>
SQUARE_ENVIRONMENT=sandbox
```

4. Restart the local server, or deploy the Site after configuring runtime values. Open Inventory, select a Square location, and refresh the counts.

The environment defaults to `sandbox`. Set `SQUARE_ENVIRONMENT=production` only with a production access token for the intended merchant. Unsupported environment values are rejected. The API version is pinned to `2026-09-16`.

Personal sandbox tokens can have broad permissions even though this implementation only reads. For a scoped OAuth sandbox token, the required scopes are `MERCHANT_PROFILE_READ`, `ITEMS_READ`, and `INVENTORY_READ`. This prototype does not implement merchant OAuth onboarding, token refresh, or multiple merchant accounts. Use Square OAuth and isolated server-side token storage before onboarding independent businesses.

## What the data means

- Counts refer to Square item **variations** at the selected location. SKU is optional and is not used as an identity key.
- Parent-item and variation location availability are respected. A location-specific tracking setting overrides the global setting.
- A missing count is **unknown**, not zero. An untracked variation is shown separately. Fractional and negative quantities are preserved.
- A low-stock flag compares the recorded count with the local threshold. Zero or a negative count gets an out-of-stock flag. This is a stock flag, not a promise that an item can be purchased: Square also has separate sold-out settings and other availability conditions.
- Counts update when the owner refreshes. The snapshot time records the completed fetch; each count can have an older Square update time. A refresh failure leaves any displayed earlier snapshot explicitly stale.
- Thresholds save only in this browser and are scoped by data source, environment, location, and variation. The default is 5. They do not change Square reorder settings or counts.
- CSV export includes all items in the displayed location snapshot. It includes data-source and snapshot timestamps. Imported text is escaped to prevent spreadsheet formula execution.
- Sample inventory is fictional and is entered explicitly. A failed Square request never silently becomes sample data.

## Server contract

`GET /api/inventory/square` returns connection metadata and active locations. When no token is configured, it returns `configured: false` and no locations. Metadata never includes the token.

`GET /api/inventory/square?locationId=<active-location-id>` returns the same metadata plus a full inventory snapshot. The location is checked against the connected merchant's active locations. The implementation follows catalog/count cursors and batches count requests; errors or safety limits fail the refresh instead of presenting a partial snapshot as complete.

The server calls:

- `GET /v2/locations`
- `GET /v2/catalog/list?types=ITEM,ITEM_VARIATION`
- `POST /v2/inventory/counts/batch-retrieve` with `states: ["IN_STOCK"]`

The last endpoint is a read operation despite its HTTP method. No Square stock, catalog, payment, or order mutations are implemented. Data is sent only to the fixed Square sandbox or production API host. Tokens stay on the server. API responses use `Cache-Control: no-store`.

This is a **single-merchant, owner-private prototype**. Its API uses the private Sites access boundary. Do not make the Site public or deploy this shared merchant endpoint publicly elsewhere without server-side authentication and merchant authorization. Browser-local thresholds are not a shared inventory database. Webhooks, automatic background sync, sales forecasting, ingredient/recipe depletion, purchase orders, and stock adjustments are not included.

## Verification

```sh
npx tsc --noEmit
node --test tests/backend.test.mjs tests/inventory.test.mjs
npm run build
```

Offline tests use mocked Square responses, never real tokens or paid API calls. A successful offline check does not establish that a merchant account is connected. Live account validation requires a configured Square token and seeded catalog/counts.

## Official sources

- [Sandbox overview](https://developer.squareup.com/docs/devtools/sandbox/overview)
- [Access tokens](https://developer.squareup.com/docs/build-basics/access-tokens)
- [API versioning](https://developer.squareup.com/docs/build-basics/versioning-overview)
- [List locations](https://developer.squareup.com/reference/square/locations-api/list-locations)
- [List catalog](https://developer.squareup.com/reference/square/catalog-api/list-catalog)
- [Batch retrieve inventory counts](https://developer.squareup.com/reference/square/inventory-api/batch-retrieve-inventory-counts)
- [Inventory count](https://developer.squareup.com/reference/square/objects/InventoryCount)
- [Variation tracking overrides](https://developer.squareup.com/reference/square/objects/CatalogItemVariation)
- [Catalog location availability](https://developer.squareup.com/reference/square/objects/CatalogObject)
- [Sold-out status](https://developer.squareup.com/docs/inventory-api/monitor-sold-out-status-on-item-variation)
