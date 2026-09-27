# U-Tender

Drawings in. Offers out. A sealed-bid tender marketplace connecting building
owners with contractors, gated by an admin-reviewed document verification
step.

**Stack:** FastAPI (Python) backend · React (Vite) frontend · MySQL ·
file storage that defaults to local disk and switches to S3 through
configuration alone.

This is a restack of the original Next.js/Supabase version of this app onto
a Python/React/MySQL foundation, with the same business rules — see
[`ARCHITECTURE.md`](#architecture-notes) below for what changed and why.

## Repo layout

```
backend/    FastAPI + SQLAlchemy + Alembic + MySQL
frontend/   React 18 + Vite + TypeScript + React Router + TanStack Query
```

## Setup

**Windows, one click:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
if you haven't already, make sure it's running, then double-click
`install.bat` in the repo root. It creates `backend/.env` for you (with
random secrets already filled in) and starts everything. Safe to run
again any time — it won't overwrite an existing `.env`, and it's how you
start the app back up after a reboot too.

**With Docker (any OS):**

```
cp backend/.env.example backend/.env
# fill in JWT_SECRET, STORAGE_SIGNING_SECRET, CRON_SECRET at minimum —
# see backend/.env.example for what each variable does
docker compose up --build
```

This starts MySQL, runs the Alembic migration automatically on backend
startup, and serves the API on `http://localhost:8000` and the frontend on
`http://localhost:5173`.

**Deploying to a real server:** SSH in (e.g. with PuTTY on Windows), clone
this repo, and run `./deploy.sh` from the repo root. It installs Docker if
needed, detects the server's public IP, creates `backend/.env` with that
IP filled in and random secrets generated, then builds and starts a
production setup: the frontend as a real nginx-served build (not the dev
server `docker-compose.yml` uses) on port 80, and MySQL is not published
to the internet at all — see `docker-compose.prod.yml` for exactly what
changes. Safe to run again later; it's also how you start the app back up
after a reboot.

**Without Docker:**

1. **Database** — run a local MySQL 8.x instance and create a database/user
   matching `backend/.env`'s `DATABASE_URL` (defaults to
   `utender`/`utender`/`utender` on `localhost:3306`).
2. **Backend:**
   ```
   cd backend
   cp .env.example .env   # fill in the secrets
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
3. **Frontend:**
   ```
   cd frontend
   cp .env.example .env   # VITE_API_URL, defaults to http://localhost:8000
   npm install
   npm run dev
   ```
4. **Create your first admin:** sign up normally through the app (as an
   owner or contractor), then update that row's `role` column to `admin`
   directly in MySQL. There's no self-serve admin signup by design. (The
   `owner_profiles`/`contractor_profiles` row created at signup stays
   behind on that account — harmless, and every admin list/detail
   endpoint filters by the user's *current* role, so a promoted admin
   never shows up as a manageable owner or contractor.)

## Demo data

`backend/scripts/seed_kuwait_demo.py` populates a running instance with a
realistic Kuwait-flavored dataset — owners, contractors, and projects
across every lifecycle state (draft, open, sealed, under evaluation,
awarded with a review, no-award) plus the admin-moderation states
(a pending owner, a pending contractor, a suspended contractor, an
admin-suspended project, and an admin-suspended offer) — everything
needed to click through the app right after a deploy. It drives the real
API (not direct DB writes), so it needs an admin account to already
exist:

```
cd backend
pip install requests   # if not already installed
python scripts/seed_kuwait_demo.py --api-url http://localhost:8000 \
    --admin-email you@example.com --admin-password 'yourpassword'
```

Point `--api-url` at wherever the backend is actually reachable (e.g. the
port `deploy-native.sh` picked on a live server). Safe to run more than
once for the accounts themselves — an email that already exists just gets
logged into instead of re-registered — but not for projects/offers, which
have no natural key to dedupe against and would be created a second time;
run it once against a database that doesn't already have this demo data.
Everyone it creates shares the password printed at the end of the run.

## Running tests

The backend has a real pytest suite under `backend/tests/` — one module per
implementation pass, covering auth, the payment gate, tender lifecycle,
sealed-bid privacy, bidding/revisions, award, notifications, security
hardening, and the file-repository storage backends (local + S3, the
latter via `moto`), plus a couple of full multi-actor end-to-end business
scenarios. Each test gets its own fresh in-memory SQLite database and
local-storage root (see `backend/tests/conftest.py`), so nothing needs a
running MySQL instance or Docker to run:

```
cd backend
python -m venv .venv && source .venv/bin/activate   # if you haven't already
pip install -r requirements-dev.txt                  # installs requirements.txt + pytest/moto
pytest
```

There is no frontend test suite yet; `npx tsc -b --noEmit` and
`npx vite build` from `frontend/` are the closest thing to a check today.

## File storage — local by default, S3 through configuration

Set in `backend/.env`:

```
STORAGE_BACKEND=local   # or "s3"
```

- **`local`** (default): files are written under `STORAGE_ROOT` on the
  backend's own disk (a bind-mounted Docker volume in `docker-compose.yml`).
  "Signed" download URLs are HMAC-signed and verified by the backend's own
  `/files` route, so they expire the same way a real signed URL does.
- **`s3`**: set `S3_BUCKET_DRAWINGS`, `S3_BUCKET_DOCUMENTS`,
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `S3_REGION` /
  `S3_ENDPOINT_URL` (the latter also works against an S3-compatible host
  like MinIO for local testing). No code change is needed to switch —
  every caller goes through the same `Storage` interface
  (`backend/app/services/storage.py`).

Drawing links stay valid for as long as the owner said bidding is open:
expiry is tied to the project's `bid_deadline` (floored at 1 hour, capped at
90 days), the same rule under either storage backend.

## Stripe and email

- **Stripe**: create one product with monthly/annual recurring prices, put
  the price IDs in `STRIPE_PRICE_ID_MONTHLY` / `STRIPE_PRICE_ID_ANNUAL`. For
  local testing, run `stripe listen --forward-to localhost:8000/billing/webhook`
  and put the printed signing secret in `STRIPE_WEBHOOK_SECRET`. In
  production, point a Stripe webhook at
  `https://yourdomain.com/billing/webhook` for
  `checkout.session.completed`, `customer.subscription.updated`, and
  `customer.subscription.deleted`.
- **Email**: set `RESEND_API_KEY` and a verified `EMAIL_FROM` address.
  Without a key, emails are logged and skipped rather than failing the
  request that triggered them.

## Deadline-reminder cron

`GET /cron/deadline-reminders` (header `Authorization: Bearer <CRON_SECRET>`)
emails owners when a project's deadline is under 24 hours away. It's
intentionally host-agnostic — point any scheduler at it (system cron, a
GitHub Actions scheduled workflow, etc.) roughly once an hour.

## Architecture notes

This app was restacked from Next.js/Supabase onto Python/React/MySQL. The
business rules carried over 1:1 — same data model, same award transaction,
same ratings recompute-from-scratch, same zip-aware drawing upload, same
signed-URL expiry tied to the bid deadline. Two things changed on purpose:

- **Authorization moved entirely into the FastAPI app layer.** The original
  app used Postgres Row Level Security as a second enforcement point,
  independent of the app code. MySQL has no RLS equivalent, so every
  ownership and eligibility check (approved, subscribed, not suspended)
  that used to live in a database policy now lives in `backend/app/deps.py`
  and the route handlers themselves. There's no separate scoped credential
  a client can call directly here — every request goes through this same
  app — so the checks are centralized in one layer instead of two, not
  weakened relative to what a client could actually reach.
- **Signup no longer requires email confirmation.** The original app relied
  on Supabase Auth's forced confirm-by-email step; this app now owns
  authentication itself (JWT access/refresh tokens in httpOnly cookies),
  and signup logs the user in immediately. Re-adding email verification is
  a reasonable follow-up but wasn't part of the stack change requested.

## Security notes

- **Sessions**: JWT access tokens (short-lived, default 30min) and refresh
  tokens (default 30 days) in httpOnly cookies. `/auth/refresh` rotates the
  refresh token and revokes the one just used; `/auth/logout` revokes
  whichever refresh token the browser sent. Revoked jtis live in the
  `revoked_tokens` table — nothing prunes rows past their own expiry yet,
  so that table grows unbounded over time; a periodic cleanup job (delete
  where `expires_at < now()`) is a reasonable follow-up before this sees
  real traffic. Access tokens are *not* checked against that table on every
  request (that would mean a DB hit per request) — logout is only
  guaranteed to close a session within one access-token lifetime, not
  instantly.
- **Passwords**: bcrypt via passlib. Signup rejects passwords over 72 bytes
  with a clear validation error rather than silently truncating (bcrypt's
  own limit).
- **Request size**: capped at `MAX_UPLOAD_MB` (default 50MB) by
  `app/middleware.py`, checked against `Content-Length` before any body is
  read into memory.
- **No rate limiting** on `/auth/login` or `/auth/signup` yet — nothing here
  slows down credential-stuffing or brute-force attempts beyond bcrypt's
  own cost factor. Worth adding (e.g. a per-IP/per-email limiter) before
  a public launch.
- **Error responses** never echo exception internals: unhandled exceptions
  are logged server-side and return a generic 500; the Stripe webhook
  handler logs its own failures rather than reflecting them back to Stripe.

## Notes for whoever picks this up next

- Document/drawing uploads should never be served from a public bucket or
  directory — both storage backends serve files through signed, expiring
  URLs only.
- `contractor_documents.status` transitions and `document_requirements`
  soft-delete (`is_active = false` instead of a hard delete) both carry
  over unchanged, so existing audit history stays intact.
- Backend has a real pytest suite (see "Running tests" above); there's no
  frontend test suite yet beyond `tsc`/`vite build`.
