# Deployment

The system is two independent services plus a database:

| Service | What it is | Needs |
|---|---|---|
| **API** | FastAPI (`backend/`, Docker image provided) | PostgreSQL, persistent disk for `uploads/` and `backups/`, 3 secrets |
| **Web** | Next.js standalone server (`frontend/`, Docker image provided) or Vercel | `NEXT_PUBLIC_API_URL` at **build** time |
| **DB** | PostgreSQL 14+ | daily backups |

## Production checklist

- [ ] `ENVIRONMENT=production` and `DEBUG=false` (the API refuses to start otherwise-weak configs: dev secrets, `DEBUG`, wildcard CORS).
- [ ] Three **different** random secrets ≥ 32 chars: `SECRET_KEY`, `JWT_SECRET`, `REFRESH_TOKEN_SECRET` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- [ ] `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db` with a dedicated least-privilege DB user. SQLite is for development only.
- [ ] `CORS_ORIGINS=https://shop.example.com` (exact origins, comma-separated) and `FRONTEND_URL=https://shop.example.com`.
- [ ] `NEXT_PUBLIC_API_URL=https://api.example.com`, `NEXT_PUBLIC_SHOW_DEMO_LOGINS=false` — rebuild the frontend after changing them.
- [ ] Serve both over **HTTPS** (Caddy/nginx/Cloudflare or the platform's TLS). The API sends `Strict-Transport-Security` when `ENVIRONMENT=production`.
- [ ] Run migrations explicitly: `python -m app.cli migrate` (Compose does it in the `migrate` service). Production never auto-migrates.
- [ ] Create the first user: `python -m app.cli create-superadmin --email you@shop.com --name "Owner"` — **do not run `seed.py`** (it refuses in production). Enable 2FA on that account (My profile).
- [ ] Persist the `uploads/` and `backups/` directories (volumes) — product images and expense receipts live there.
- [ ] Configure SMTP (`SMTP_*`) if you want password-reset emails; without it the reset link is only written to the server log in development and **not delivered** in production.
- [ ] Schedule backups (below) and copy them off the server.
- [ ] Put a rate-limiting proxy/WAF in front if you run more than one API instance (the built-in limiter is per process).
- [ ] Set the shop profile, tax rates, payment methods and register names under **Settings** before trading.

## Docker Compose (single server / VPS)

```bash
cp .env.example .env      # set POSTGRES_PASSWORD, SECRET_KEY, JWT_SECRET, REFRESH_TOKEN_SECRET, CORS_ORIGINS, NEXT_PUBLIC_API_URL
docker compose up -d --build
docker compose run --rm backend python -m app.cli create-superadmin --email owner@yourshop.com --name "Shop Owner"
```
Terminate TLS with a reverse proxy (Caddy example):
```
shop.example.com { reverse_proxy frontend:3000 }
api.example.com  { reverse_proxy backend:8000 }
```
Upgrades: `git pull && docker compose up -d --build` (the `migrate` service runs first).

## Platform recipes

| Platform | API | Web | Database |
|---|---|---|---|
| **Render** | *Web Service* from `backend/` (Docker). Pre-deploy command `python -m app.cli migrate`. Add a **Disk** mounted at `/app/uploads` and `/app/backups`. | *Web Service* from `frontend/` (Docker) or Static/Node, build args `NEXT_PUBLIC_API_URL` | Render PostgreSQL (`DATABASE_URL` → use the `postgresql+psycopg://` scheme) |
| **Railway** | Service from `backend/` Dockerfile, Volume at `/app/uploads`, release command `python -m app.cli migrate` | Service from `frontend/` Dockerfile, build variable `NEXT_PUBLIC_API_URL` | Railway Postgres plugin |
| **Vercel** (frontend only) | host the API elsewhere | Import `frontend/` as a Next.js project; set `NEXT_PUBLIC_API_URL`. The API must allow the Vercel domain in `CORS_ORIGINS`. | Neon / Supabase / RDS for Postgres |
| **AWS** | ECS Fargate or App Runner from the backend image; EFS or S3 for uploads (mount EFS at `/app/uploads`) | ECS/App Runner from the frontend image, or Amplify | RDS PostgreSQL, automated backups on |
| **DigitalOcean** | App Platform (Docker) or a Droplet with the Compose file | same | Managed PostgreSQL |

Anywhere: the only runtime dependency of the API besides the database is the writable upload/backup directories.

## Backups & restore

**Built in (Settings → Backup & restore, Super Admin only):** *Back up now* creates a consistent snapshot in `BACKUP_DIR` (SQLite online-backup API; PostgreSQL via `pg_dump -Fc`, included in the Docker image). Download copies off-site. *Restore* replaces the live data after taking a `-prerestore` safety copy.

**Recommended for PostgreSQL — nightly cron on the DB host:**
```bash
# backup
pg_dump -Fc "$DATABASE_URL_PLAIN" > /backups/shop-$(date +%Y%m%d-%H%M%S).dump
# keep 30 days
find /backups -name 'shop-*.dump' -mtime +30 -delete

# restore into an empty/target database
pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL_PLAIN" /backups/shop-YYYYMMDD-HHMMSS.dump
```
(`DATABASE_URL_PLAIN` is the `postgresql://…` form of the URL.) Test a restore on a scratch database at least once. Also back up `uploads/`.

**SQLite (development / very small shops):** copy the `.db` file while the API is stopped, or use the in-app backup.

## Monitoring

* `GET /health` → `{"status": "healthy", "checks": {"app": "ok", "database": "ok"}}` (HTTP 503 when the database is unreachable). Used by the Docker `HEALTHCHECK`; point your uptime monitor at it.
* Every response carries `X-Request-ID`; the same id is in the access log and in the `request_id` field of error bodies, so a user-reported error can be found in the logs. Stack traces are logged, never returned to clients.

## Upgrading the schema

1. Change models → `alembic revision --autogenerate -m "describe change"` → review the file.
2. Run tests (a test fails if models and migrations disagree).
3. Deploy; the `migrate` step applies it. Take a backup first.
