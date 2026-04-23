# MBL Backend — Building Maintenance System

FastAPI backend for the **Maison Benoît Labre Building Maintenance System** (frontend
app `mbl-frontend`).

## What it is

A small REST API with JWT-based auth. Used by the React frontend to manage
apartments, common areas, maintenance requests, scheduled tasks, suppliers,
employees, inventory, assets, tools, remarks, historical records, and analytics.

## Stack

- **Python 3.11+**
- **FastAPI**
- **SQLite** for storage (single file in `/data/mbl.sqlite3`)
- **JWT** auth (`python-jose`)
- **bcrypt** password hashing (`passlib`)

SQLite is fine for a single-instance deployment on a persistent volume (Fly.io
volumes, AWS EBS, etc.). For heavier workloads or multi-instance, migrate to
managed Postgres — see "Migrating to Postgres" below.

## Running locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
MBL_DATA_DIR=./data MBL_JWT_SECRET=dev-secret uvicorn app.main:app --reload
```

Seeded accounts on first run:

| Email                                          | Password         | Role  |
| ---------------------------------------------- | ---------------- | ----- |
| `admin@mbl.com`                                | `Admin2025!`     | admin |
| `andreanedesilets@lamaisonbenoitlabre.org`     | `Andreanne2025!` | admin |
| `faycal@lamaisonbenoitlabre.org`               | `Faycal2025!`    | admin |
| `hicham@lamaisonbenoitlabre.org`               | `Hicham2025!`    | admin |

**Change these passwords in production.**

## Environment variables

| Name             | Default                      | Purpose                              |
| ---------------- | ---------------------------- | ------------------------------------ |
| `MBL_DATA_DIR`   | `/data`                      | Directory for the SQLite DB file     |
| `MBL_JWT_SECRET` | `mbl-dev-secret-change-me`   | HMAC secret for signing JWTs. **Must be set in production.** |

## Deploying to production

This repo is designed to deploy to **Fly.io** with an attached persistent
volume. Fly's hobby plan covers a small always-on instance for roughly
$2–3 / month; Fly volumes include automatic daily snapshots (5-day retention)
which cover backups for a small NGO workload.

### 1. Install flyctl and log in

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 2. Create the app (one-time)

```bash
fly launch --no-deploy --name mbl-backend-<yourname>
# (answer "no" to Postgres and Redis prompts)
fly volumes create mbl_data --size 1 --region yul   # pick a region near you
fly secrets set MBL_JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
```

Edit `fly.toml` so the mount block points at `/data`:

```toml
[[mounts]]
  source = "mbl_data"
  destination = "/data"
```

### 3. Deploy

```bash
fly deploy
```

### 4. Backups

Fly volumes are snapshotted daily automatically with 5-day retention. To list
or restore snapshots:

```bash
fly volumes snapshots list <volume-id>
fly volumes snapshots create <volume-id>   # manual snapshot before risky changes
```

For longer retention, copy the SQLite file off-site nightly with a cron on Fly
(`fly machine exec`) or with a GitLab CI scheduled job.

## Migrating to Postgres (when you outgrow SQLite)

1. Provision managed Postgres — the free tier on [Neon](https://neon.tech) is
   generous (3 GB, automatic point-in-time recovery).
2. Replace the raw `sqlite3` calls in `app/main.py` with SQLAlchemy (drop-in
   rewrite — the schema is already portable). Set `DATABASE_URL` as a secret.
3. One-time data migration: use [pgloader](https://pgloader.io) to copy from
   the SQLite file to Postgres.

Not needed for launch. Leave this for when traffic grows.

## API overview

All endpoints are under `/api`. All routes except `/api/auth/login` require a
`Authorization: Bearer <token>` header.

- `POST /api/auth/login` → `{ token, user }`
- `GET /api/auth/me`
- `POST /api/auth/register` *(admin only)* — create employee
- `GET /api/user/is-approver`
- `GET /api/dashboard`
- `GET /api/apartments`, `GET /api/apartments/work-status`
- `GET /api/common-areas`
- `GET /api/suppliers`
- `GET /api/employees`
- `GET /api/inventory`, `GET /api/inventory/low-stock`
- `GET /api/assets`
- `GET /api/tools`
- `GET /api/remarks`
- `GET /api/maintenance`
- `GET /api/scheduled-tasks`, `/upcoming?days=14`, `/overdue`
- `GET /api/historical-records`
- `GET /api/analytics/costs`, `/yearly-summary`, `/apartment/{id}`

**Note:** only the read (GET) endpoints are implemented in this initial
restore. Create/update/delete mutation endpoints will need to be added back
before end users can enter data through the UI. See `app/main.py` for the
exact contract the frontend expects.
