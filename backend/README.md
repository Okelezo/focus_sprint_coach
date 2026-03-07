# Focus Sprint Coach (Backend)

## Prerequisites

- Docker + Docker Compose
- (Optional for running without Docker) Python 3.11+

## Quickstart (Docker)

1) Create a local env file:

```bash
cp .env.example .env
```

2) Start Postgres + API:

```bash
make dev
```

3) Run migrations (in another shell):

```bash
docker-compose exec api alembic upgrade head
```

4) Verify health:

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

## Local development (without Docker)

1) Create a venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

2) Run DB (still easiest via docker):

```bash
docker-compose up -d db
```

3) Run migrations:

```bash
alembic upgrade head
```

4) Start API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API

### Auth

- `POST /auth/register`
- `POST /auth/login` (returns JWT access token)
- `GET /me`

Example:

```bash
curl -sS -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password"}'

TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sS http://localhost:8000/me -H "Authorization: Bearer ${TOKEN}"
```

### Tasks

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/microsteps`

### Sprints

- `POST /sprints/start`
- `POST /sprints/{sprint_id}/events`
- `POST /sprints/{sprint_id}/finish`
- `POST /sprints/{sprint_id}/reflection`

### History + Stats

- `GET /history/today`
- `GET /stats/summary`

### AI

- `POST /ai/breakdown`
- `POST /ai/blocker_recovery`

Example:

```bash
TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sS -X POST http://localhost:8000/ai/breakdown \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"task_title":"Write a project README","context":"Keep it short and practical"}'
```

## Acceptance checklist

From scratch (fresh DB volume):

```bash
docker-compose up -d --build
docker-compose exec -T api alembic upgrade head
docker-compose exec -T api pytest
```

Manual UI smoke:

- **Login/Register**: `GET /`
- **Tasks**: `GET /app`
- **Task detail**: `GET /app/task/{id}`
- **Sprint**: `GET /app/sprint`
- **Today history**: `GET /app/history`

## UI notes (dark theme)

- **Stylesheet**
  - `app/ui/static/styles.css`
  - Uses CSS variables for design tokens (e.g. `--bg`, `--surface`, `--text`, `--muted`, `--accent`, `--danger`).

- **Layout / app shell**
  - Base layout: `app/ui/templates/base.html`
  - App bar: `app/ui/templates/partials/appbar.html`
  - Primary nav: `app/ui/templates/partials/nav.html`
  - Toast: `app/ui/templates/partials/toast.html`

- **Tasks page**
  - Page: `app/ui/templates/app.html`
  - Task row card: `app/ui/templates/partials/task_row.html`

- **HTMX micro-interactions**
  - Loading indicators use `.htmx-indicator` + `.htmx-hide-when-request` and are styled in `styles.css`.
  - Toasts can be triggered in-page via `window.fscToast('...')`.

## Observability

### Analytics

For MVP, `track(user_id, event_name, props)` writes to Postgres `analytics_events`.

Optional: also forward to PostHog when both are set:

- `POSTHOG_API_KEY`
- `POSTHOG_HOST` (e.g. `https://app.posthog.com`)

### Error monitoring (Sentry)

Set:

- `SENTRY_DSN`

When set, the API initializes Sentry and captures unhandled exceptions. Request cookies/headers/body are scrubbed before sending.

### Funnel queries (Postgres)

Example: registrations -> first task created -> first AI breakdown:

```sql
WITH first_event AS (
  SELECT
    user_id,
    event_name,
    MIN(created_at) AS first_at
  FROM analytics_events
  WHERE event_name IN ('user_registered', 'task_created', 'ai_breakdown_called')
  GROUP BY user_id, event_name
)
SELECT
  COUNT(*) FILTER (WHERE event_name = 'user_registered') AS registered,
  COUNT(*) FILTER (WHERE event_name = 'task_created') AS created_task,
  COUNT(*) FILTER (WHERE event_name = 'ai_breakdown_called') AS called_ai
FROM first_event;
```

Example: AI success rate over last 7 days:

```sql
SELECT
  date_trunc('day', created_at) AS day,
  COUNT(*) AS calls,
  COUNT(*) FILTER (WHERE (props->>'success')::boolean IS TRUE) AS success,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE (props->>'success')::boolean IS TRUE) / NULLIF(COUNT(*), 0),
    1
  ) AS success_pct
FROM analytics_events
WHERE event_name = 'ai_breakdown_called'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

## Tooling

- Format:

```bash
make fmt
```

- Lint + types:

```bash
make lint
```

- Tests:

```bash
make test
```

## Migrations

- Create a new migration:

```bash
make migrate
```

- Apply migrations:

```bash
make upgrade
```

## Deploy checklist

- **Set required env vars**:
  - `DATABASE_URL`
  - `JWT_SECRET_KEY`
  - `OPENAI_API_KEY` (if using AI features)
  - `CORS_ORIGINS` (comma-separated)
  - `UI_COOKIE_SECURE=true` (recommended in prod)
  - `UI_COOKIE_SAMESITE=lax` (or `strict` depending on your setup)
  - `GIT_SHA` and `BUILD_TIMESTAMP` (for `/version`)

- **Optional observability**:
  - `SENTRY_DSN`
  - `POSTHOG_API_KEY`
  - `POSTHOG_HOST`

- **Bring up the stack**:
  - `docker-compose up -d --build`
  - `docker-compose exec -T api alembic upgrade head`

- **Smoke test**:
  - `GET /health`
  - `GET /version`
  - UI login/register flow

## Railway (Dockerfile) deployment

- **Runtime behavior**
  - The container entrypoint is `start.sh`.
  - On start, it runs `alembic upgrade head` (idempotent) and then starts Uvicorn bound to `0.0.0.0:$PORT` (defaults to `8000` locally).

- **Required env vars (production)**
  - `ENVIRONMENT=production`
  - `DATABASE_URL` (Railway typically provides this when a Postgres resource is attached)
  - `JWT_SECRET_KEY` (**do not** use the default)
  - `APP_BASE_URL` (your Railway domain, e.g. `https://<service>.up.railway.app`)
  - `CORS_ALLOW_ORIGINS` (comma-separated list)
  - `UI_COOKIE_SAMESITE=lax`
  - `UI_COOKIE_SECURE=true` (recommended)
  - `POSTHOG_API_KEY` and `POSTHOG_HOST` (optional)
  - `SENTRY_DSN` (optional)
  - `BUILD_TIME` (optional)
  - `GIT_SHA` or `RAILWAY_GIT_COMMIT_SHA` (optional)

- **Smoke test (end-to-end)**
  - Register → login → create task → AI breakdown → start sprint → log distraction → finish → reflection → view history.
  - Verify:
    - `GET /health` returns `{"status":"ok"}`
    - `GET /version` returns build metadata

- **Verify analytics in Postgres**

```sql
SELECT created_at, user_id, event_name, props
FROM analytics_events
ORDER BY created_at DESC
LIMIT 50;
```
