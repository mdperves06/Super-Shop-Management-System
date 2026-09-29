# Super Shop Management System

A full-stack point-of-sale, inventory, purchasing and accounting platform for a Bangladeshi supermarket — POS with barcode scanning, batch/expiry-aware stock, suppliers and customers with ledgers, cash-register reconciliation, VAT, reports, audit trail and role-based access. English and বাংলা.

| | |
|---|---|
| **Frontend** | Next.js 16 (App Router) · TypeScript · React 19 · Tailwind CSS 4 · shadcn/ui (Base UI) · TanStack Query · React Hook Form + Zod · Recharts |
| **Backend** | Python 3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · JWT (access + rotating refresh) · Argon2 |
| **Database** | PostgreSQL in production · SQLite for local development (same code, same migrations) |
| **Ops** | Docker Compose (frontend, backend, postgres) · health checks · scripted backups |

> **Demo data & credentials** are for local development only. `seed.py` creates users with the public password `Demo@12345`. Never seed a real installation — use `python -m app.cli create-superadmin` instead.

---

## Quick start (local, no Docker)

Requirements: **Python 3.11+** (tested on 3.13), **Node.js 20+** (tested on 24), npm.

```bash
# 1. backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
python seed.py --reset            # creates shop.db, runs migrations, loads demo data (~30 s)
uvicorn app.main:app --reload     # http://localhost:8000  (docs at /docs)

# 2. frontend (second terminal)
cd frontend
cp .env.example .env.local        # Windows: copy .env.example .env.local
npm install
npm run dev                       # http://localhost:3000
```

Windows shortcuts: `run_backend.bat`, `run_frontend.bat` (or `run_all.bat`). Linux/macOS: `./run_backend.sh`, `./run_frontend.sh`.

Sign in at http://localhost:3000 with any demo account (password `Demo@12345`):

| Account | Role | Lands on |
|---|---|---|
| `admin@example.com` | Owner / Admin | Dashboard |
| `manager@example.com` | Manager | Dashboard |
| `cashier@example.com` (`cashier2@`) | Cashier | Dashboard → POS |
| `inventory@example.com` | Inventory manager | Dashboard |
| `accountant@example.com` | Accountant | Dashboard |
| `superadmin@example.com` | Super admin (backups, roles) | Dashboard |
| `staff@example.com` | Staff (read-only) | Dashboard |

## Run with Docker

```bash
cp .env.example .env              # then edit: POSTGRES_PASSWORD and the three secrets
docker compose up --build
```

`migrate` applies Alembic migrations, then `backend` (port 8000) and `frontend` (port 3000) start. Create the first user:

```bash
docker compose run --rm backend python -m app.cli create-superadmin --email owner@yourshop.com --name "Shop Owner"
```

Production notes are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## What's inside

| Area | Highlights |
|---|---|
| **POS** | Barcode scanner (USB keyboard-wedge) or search, category filter, quantity/discount editing, walk-in or registered customer, cash / card / bKash / Nagad / Rocket / bank, **split payments**, change calculation, credit sales with limits, promotions applied automatically, thermal receipt + A4 + PDF, idempotent checkout |
| **Inventory** | Per-batch stock with expiry (FEFO) and FIFO costing, immutable stock ledger for *every* movement, low-stock / out-of-stock / expiring / expired views, damage & expiry write-offs, mandatory adjustment reasons |
| **Purchasing** | Draft → pending → approved → (partially) received; stock and the supplier payable are created **only on receipt**; purchase returns; supplier payments and ledger |
| **Customers & suppliers** | Ledgers with running balance, credit limits, opening balances, payment collection, statements (PDF) |
| **Returns** | Linked to the original invoice (never edits it), restocks the exact batches, refunds via any method, reduces unpaid balance first |
| **Finance** | Expenses (with receipt upload), cash register open/close with expected-vs-counted reconciliation and required discrepancy reason, VAT with effective dates, profit & loss, cash flow, payables/receivables |
| **Reports** | 22 reports with date/product/category/supplier/cashier/payment filters, CSV + Excel export, print |
| **Dashboard** | KPI cards, sales/profit trend, top products, category and inventory donuts, recent transactions; content follows the user's permissions |
| **Security** | RBAC with 65 granular permissions enforced server-side, Argon2 passwords, JWT + single-use rotating refresh tokens, lockout, rate limiting, TOTP 2FA, audit log, secure headers, validated uploads |
| **Ops** | Health endpoint, backup/restore, CSV import with validation and dry-run, Docker, Alembic migrations |
| **Localisation** | ৳ BDT, Asia/Dhaka time zone, lakh/crore digit grouping, configurable date format, English/বাংলা UI (translation files in `frontend/messages`) |

Documentation:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, key design decisions, business rules
- [docs/FINANCE.md](docs/FINANCE.md) — how revenue, COGS, profit, VAT, ledgers and cash are calculated
- [docs/API.md](docs/API.md) — every endpoint (also live at `/docs`)
- [docs/DATABASE.md](docs/DATABASE.md) — every table and column
- [docs/PERMISSIONS.md](docs/PERMISSIONS.md) — permission catalogue and default roles
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — production checklist, Render/Railway/Vercel/AWS/DigitalOcean, backups & restore
- [docs/TESTING.md](docs/TESTING.md) — test suites and the manual acceptance scenario

## Development commands

```bash
# backend (from backend/)
pytest                                   # 88 tests: auth, RBAC, catalogue, inventory, purchasing, POS, returns,
                                         # cash register, reports, imports, backups, concurrency, migrations
ruff check .                             # lint
alembic revision --autogenerate -m "…"   # new migration after changing models
alembic upgrade head                     # apply migrations (production does this explicitly)
python seed.py --reset                   # demo data (SQLite only)
python scripts/gen_docs.py               # regenerate docs/API.md, DATABASE.md, PERMISSIONS.md

# frontend (from frontend/)
npm run dev | build | start
npm run typecheck && npm run lint
npm test                                 # vitest: formatting, API client, payment settlement, tables, login
```

## Environment variables

See [.env.example](.env.example) for the full annotated list. The important ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/db`. Unset → local SQLite file. |
| `SECRET_KEY`, `JWT_SECRET`, `REFRESH_TOKEN_SECRET` | Independent random secrets, ≥ 32 chars. **The API refuses to boot in production with the development defaults.** |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API (no `*` in production). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime (default 30). |
| `UPLOAD_DIR`, `BACKUP_DIR` | Where product images / receipts / backups are stored (persist these volumes). |
| `NEXT_PUBLIC_API_URL` | API base URL as seen from the browser; baked into the frontend build. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Login page says *Cannot reach the server* | Backend not running or `NEXT_PUBLIC_API_URL` wrong. Check http://localhost:8000/health. |
| Browser console shows a CORS error | Add the frontend origin to `CORS_ORIGINS` and restart the API. |
| `database is locked` on SQLite | Only one API process should write to a SQLite file; use PostgreSQL for multi-worker deployments. |
| `Refusing to seed demo data in production` | By design. Seed only development databases. |
| `pg_dump is not installed` when backing up | Install `postgresql-client` on the API host (already in the Docker image) or run the documented `pg_dump` command yourself. |
| Bangla text looks like boxes in PDFs | Built-in PDF fonts lack Bangla; PDFs use English text and "Tk". On-screen/print views render Bangla natively. |
| Barcode scanner types into the wrong place | On the POS the scan box regains focus on any key; press **F2** to focus it manually. |
| Port 3000/8000 already in use | Stop the other process or run on other ports (`uvicorn … --port 8001`, `npm run dev -- -p 3001`; update `CORS_ORIGINS`/`NEXT_PUBLIC_API_URL`). |

## Repository layout

```
backend/   FastAPI app (app/api, services, models, schemas, repositories, middleware), alembic/, tests/, seed.py
frontend/  Next.js app (app/, features/, components/, lib/, hooks/, services/, types/, messages/, tests/)
docs/      architecture, finance rules, API, database, permissions, deployment, testing
docker-compose.yml   .env.example   run_*.bat / run_*.sh
```
