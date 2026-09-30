# Architecture & design decisions

## Layers

```
Browser (Next.js)  ──HTTPS/JSON──▶  FastAPI  ──▶  services  ──▶  SQLAlchemy models  ──▶  PostgreSQL / SQLite
   features/*                        api/v1/*      (business       (repositories/base.py
   components/*                      (routes:      rules,           = pagination helpers)
   lib/api.ts                        auth, RBAC,   atomic
                                     validation)   stock moves)
```

| Layer | Responsibility | Where |
|---|---|---|
| Routes | HTTP, auth (`require("perm")`), request/response schemas. **No business logic.** | `backend/app/api/v1/*.py` |
| Schemas | Pydantic input validation and output shaping (e.g. cost fields hidden without permission). | `backend/app/schemas/` |
| Services | All rules: pricing, stock allocation, ledgers, cash, purchasing, reports. Each public function is one unit of work. | `backend/app/services/` |
| Repositories | Shared query helpers (pagination, sorting, safe `LIKE`). | `backend/app/repositories/base.py` |
| Models | Tables, constraints, indexes, soft-delete/timestamp mixins. | `backend/app/models/` |
| Middleware | Secure headers, request-id + access log, rate limiter, CORS. | `backend/app/middleware/`, `main.py` |

Frontend: `app/` (routes, thin) → `features/<domain>/` (screens) → `components/shared` + `components/ui` (design system) → `lib/` (API client, auth, i18n, formatting) → `services/lookups.ts` (cached reference data). Types mirror the API in `types/api.ts`.

## Decisions (and why)

| Topic | Decision |
|---|---|
| **Single source of truth for money** | The server computes every price, discount, VAT, total, change, COGS, profit and balance. The POS calls `POST /sales/preview` (same code path as checkout) and only displays the result. `pricing.py` holds the cart maths; `financials.py` holds revenue/COGS/profit. |
| **Stock model** | `inventory` (per-product totals) + `inventory_batches` (units, cost, expiry) + `inventory_transactions` (immutable ledger). All movement goes through `inventory_service`; nothing edits stock directly. |
| **Concurrency** | Decrements are conditional `UPDATE … WHERE qty >= :n` (no lost updates on any database), batches are locked `FOR UPDATE` on PostgreSQL, and SQLite uses `BEGIN IMMEDIATE`. Document numbers come from an atomic counter row. Proven by tests with 8 simultaneous sellers on 5 units. |
| **Atomicity** | A sale (invoice, lines, stock, batches, payments, cash movement, customer ledger, audit) is one DB transaction; any exception rolls back everything. Test: forcing a failure after stock+payment writes leaves zero rows. |
| **Costing / valuation** | Batch costing: FIFO, or FEFO for expiry-tracked products. Sales record the exact batches consumed, so COGS and stock value are exact and returns restock the same batches. (Weighted-average is not offered — one consistent method is documented rather than two half-supported ones.) |
| **VAT** | Rates are data (`tax_rates`) with effective dates; products point at a rate. `tax.prices_include_tax` (default on, matching MRP practice) decides whether VAT is extracted from or added to the shelf price. Profit uses revenue **excluding** VAT. Purchase cost excludes recoverable input VAT; the supplier payable includes it. |
| **Purchases** | An order changes nothing. Stock **and** the supplier payable are created only by *receiving* (`GoodsReceipt`), proportionally for partial deliveries, exactly (no rounding drift) on the final one. |
| **Returns & voids** | Never edit an invoice. A return is its own record linked to the sale; a void marks the sale `VOIDED` and reverses stock, cash and ledgers. Returns reduce the sale's unpaid balance first, then refund the remainder. |
| **Deletion** | Financial records are never physically deleted. Products/suppliers/customers/employees/categories are soft-deleted (SKU stays reserved); expenses and sales are voided. |
| **Ledgers** | `supplier_transactions` / `customer_transactions` carry a running `balance_after`; the parent row's `balance` is updated atomically in the same statement sequence. A test asserts `balance == sum(ledger)` for every party. |
| **Auth** | Argon2 hashes; 30-min access JWT bound to a session row; single-use rotating refresh tokens stored hashed; logout/deactivation/password change revoke sessions server-side; lockout after 5 bad passwords; TOTP 2FA; reset tokens are single-use, 1 h. |
| **Tokens in the browser** | The short-lived access token lives only in JavaScript memory. The refresh token is an `HttpOnly`, `Secure` (production), `SameSite=Lax` cookie (`ssm_refresh`) scoped to `/api/v1/auth`, so XSS cannot read it. Refresh/logout require the custom header `X-Requested-With: ssm` (CSRF defence on top of SameSite, forces a CORS pre-flight). Rotation has a 20 s grace window so several tabs refreshing at once all succeed; logout and password changes revoke immediately with no grace. API clients can opt into a JSON body token with `X-Token-Delivery: body`. On page load the app calls `/auth/refresh` to restore the session. If web app and API are on different registrable domains set `COOKIE_SAMESITE=none` (needs HTTPS). |
| **Time** | Everything is stored as naive UTC and serialised with `Z`. "Today", weeks and months are computed in the shop time zone (default Asia/Dhaka) via `utils/dates.py` and `utils/sqlx.py`. |
| **Migrations** | One Alembic chain (`0001` creates the full schema). A test upgrades an empty DB with the migrations and asserts it equals `Base.metadata`. Production never auto-migrates: run `python -m app.cli migrate` (Compose does this in the `migrate` service). |
| **Variants** | The spec's `product_variants` table is intentionally not built: sizes/flavours are separate products (own SKU, barcode, stock), which is how barcodes and shelf stock work in practice. Add variants only if you need grouped catalogue pages. |
| **Transfers** | `TRANSFER` exists as a stock-transaction type reserved for a future multi-branch build; single-location shops don't use it. |
| **Payment gateways** | bKash / Nagad / Rocket / card are recorded payment methods (with mandatory reference), not live integrations — no external API is faked. Add a gateway adapter behind `sales_service` when credentials exist. |
| **PDFs** | Generated with fpdf2 + HarfBuzz shaping and the bundled Noto Sans Bengali (SIL OFL, `backend/app/assets/fonts`, rebuilt by `scripts/build_fonts.py`), so ৳ and Bangla conjuncts render correctly on any OS with no system fonts. Covered by a test that extracts the text and checks the embedded font. |
| **Rate limiting** | Three per-IP buckets: credentials (`login`, `forgot-password`, `reset-password`, strictest), sensitive (backups, import/export, password/2FA changes) and general API. Counters are process-local by default; set `REDIS_URL` to share them across workers and replicas (fixed one-minute window, atomic `SET NX EX` + `INCR`; if Redis is down it falls back to the local counter rather than blocking sales). Behind a proxy run uvicorn with `--proxy-headers` and `FORWARDED_ALLOW_IPS=<proxy ip>` so the client IP cannot be spoofed; a WAF/CDN in front is still recommended. |

## Business rules (all enforced server-side and covered by tests)

1. A purchase order does not change stock; only receiving does.
2. A sale decreases stock; a sale return increases it; a purchase return decreases it.
3. Every stock movement writes an `inventory_transactions` row; adjustments require a reason.
4. Overselling is rejected unless `inventory.allow_oversell` is on; expired batches can't be sold unless allowed.
5. Cashiers can't exceed the discount limit on their own: they file a discount request (`POST /discount-requests`) tied to the exact cart, a user with `discount.approve` (Manager/Admin by default, never the requester) approves or rejects with a note, and the approved request is redeemed by exactly one sale (`discount_request_id`; conditional UPDATE makes it single-use, 30-minute expiry, cart changes invalidate it). Requester, approver, timestamps, reason and outcome are stored and audited. Cashiers also can't sell on credit without `sale.credit`, can't see cost/profit, can't void, and only see their own sales.
6. Credit sales need a registered customer and available credit (`credit_limit − balance`).
7. Selling requires an open register session (configurable); closing with a different count than expected requires a written reason and raises a notification.
8. Sensitive actions (price changes, voids, adjustments, approvals, balance changes, settings, role/user changes, logins) are written to the audit log with before/after values.
9. Duplicate SKU or barcode is rejected; negative or zero quantities and negative prices are rejected on both client and server.
10. Uploads are identified by content (magic bytes), size-limited and stored under random names.
