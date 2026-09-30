# Testing

## Automated

| Suite | Command | Covers |
|---|---|---|
| Backend (pytest, real HTTP through `TestClient`, temp SQLite built **from the Alembic migration**) | `cd backend && pytest` | login, lockout, refresh rotation, password reset, 2FA · RBAC matrix & privilege escalation · products/barcodes/SKU rules · FEFO batches · purchases (partial receipt, VAT, payments, returns) · POS (cash/split/credit/change, discount cap, promotions, VAT-inclusive, void, returns, idempotency) · cash register reconciliation · expenses & uploads · customer/supplier ledgers · dashboard/report figures vs. sales · CSV import/export · backups (incl. restore round-trip) · **concurrency** (8 threads / 5 units, no overselling, unique invoice numbers) · **rollback** (forced failure leaves no partial data) · FK enforcement · migration ↔ model equality · security headers/CORS · the full acceptance scenario |
| Frontend (vitest + Testing Library) | `cd frontend && npm test` | currency/date formatting (Dhaka time, lakh grouping), API client (auth header, refresh-and-retry, logout on dead session, friendly errors), POS payment settlement, purchase-order estimate, DataTable loading/empty/error/pagination states, login form validation & server errors, i18n fallback |
| End-to-end (Playwright, real browser + real API + seeded throw-away SQLite) | `cd frontend && npm run e2e` (set `E2E_PYTHON` to the backend venv's Python; `E2E_CHANNEL=chrome` uses installed Chrome instead of `npx playwright install chromium`) | login/logout/session-survives-reload/HttpOnly cookie · password reset (single use) · product creation → purchase → approve → receive → inventory · POS cash sale and stock deduction · discount approval (request → manager approves/rejects → single-use sale) · report page + CSV download |
| PostgreSQL | `TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db pytest` (the schema is dropped and recreated — use a scratch database) | the whole backend suite on real PostgreSQL incl. row locking, `to_char` date grouping, concurrency, `pg_dump` backups. CI runs it against `postgres:16`. |
| Static | `ruff check .` · `npm run typecheck` · `npm run lint` · `npm run build` | |

## Manual acceptance scenario (also automated in `tests/test_acceptance.py`)

1. Sign in as **admin@example.com** → create a category, a supplier, a product with a barcode.
2. **Purchases → New purchase order** for 100 units → submit → approve → **Receive stock** 100. Inventory shows **100**; the supplier owes the order value.
3. Sign in as **cashier@example.com** → **POS** → *Open register* (e.g. ৳20 000) → scan the barcode → set quantity 5 → **Pay** → complete. Inventory is **95**; receipt/PDF works; the sale, payment and dashboard update.
4. Open the invoice → **Return items** 2 → refund. Inventory is **97**; the return is a separate `RET-…` record; the original invoice is unchanged.
5. **Expenses** → record a cash expense. **Cash register** → *Close register* with a count that differs from expected → a reason is required; the difference is recorded, a notification is raised and the audit log has the entry.
6. Check **Customer/Supplier ledger**, **Reports → Profit / Inventory valuation**, **Audit logs**.

Permission spot-checks: sign in as the cashier and confirm there is no Purchases/Reports/Settings/Audit menu, cost columns are absent, a 10 % discount is rejected, and calling `/api/v1/audit-logs` directly returns 403.
