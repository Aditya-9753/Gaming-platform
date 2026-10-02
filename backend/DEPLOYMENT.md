# Production, deployment, and load testing

## Environment

Copy `.env.example` to `.env` for local development. Production must provide
`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, and `JWT_REFRESH_SECRET` through the
deployment secret store. Use unique, randomly generated JWT secrets of at least
32 characters; never use the local development values in production. Set
`APP_ENV=production`, `DEBUG=false`, and `CORS_ORIGINS` to the exact trusted
frontend origins. Optional configuration includes `SENTRY_DSN`,
`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, and `DATABASE_POOL_TIMEOUT`.
Configure `CRICKET_DATA_URL` and `CRICKET_DATA_API_KEY` for the external
provider before enabling production Cricket markets; the mock provider is
development-only.

## Local setup and commands

From `backend/`, create/activate a virtual environment, install
`requirements-dev.txt`, and copy `.env.example` to `.env`. Before starting
Compose, set `POSTGRES_PASSWORD` in `.env` to the same password used in
`DATABASE_URL` (Compose needs it to initialize PostgreSQL). Start Docker Desktop,
then run:

```powershell
docker compose up -d postgres redis
docker compose ps
```

Wait until both services are healthy. Then run `alembic upgrade head` and start
the API:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the full test suite with `python -m pytest -q`. Run the game engine with
`python -m app.games.base.engine`. Run Celery worker and Beat in separate
processes:

```powershell
celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --pool=solo
celery -A app.workers.celery_app:celery_app beat --loglevel=INFO
```

## Docker and Render

The Dockerfile builds a slim multi-stage image and runs as an unprivileged
application user. Render service definitions are in `render.yaml`; provision
PostgreSQL and Redis, then configure the required secret environment variables
on every web, engine, and Celery service. Run migrations as a release/pre-deploy
command before accepting traffic. Scale API replicas independently from the
single elected game-engine leader; use only one Celery Beat scheduler.

## Backup and recovery

Take encrypted, automated PostgreSQL backups at least daily and before schema
migrations. Game server seeds remain in the database until their rounds settle,
so production must use encrypted database storage and tightly restricted DB
credentials as well as encrypted backups. Retain point-in-time recovery/WAL
archives where supported and periodically test restoration into an isolated database. Back up critical
configuration and secrets using the hosting provider's encrypted secret store;
do not put secrets in repository backups. Redis is operational state and should
not replace durable PostgreSQL records; enable Redis persistence if the
deployment relies on queued background tasks. Monitor backup completion,
reconciliation mismatches, and restore-test results.

### GitHub Actions CI/CD

The repository workflow at `.github/workflows/ci-cd.yml` runs backend compile,
migration-history, and pytest checks plus frontend lint and production build on
pull requests and pushes to `main`. Successful pushes to `main` trigger Render
only after both jobs pass. Configure the frontend static service's
`VITE_API_BASE_URL` as `https://<api-host>/api/v1` and `VITE_WS_URL` as
`wss://<api-host>/ws`; add the frontend origin to the API's `CORS_ORIGINS`.

Create Render deploy hooks for the API, engine worker, Celery worker, Celery
Beat, and frontend. Store them as GitHub Actions secrets named
`RENDER_API_DEPLOY_HOOK`, `RENDER_ENGINE_DEPLOY_HOOK`,
`RENDER_CELERY_DEPLOY_HOOK`, `RENDER_CELERY_BEAT_DEPLOY_HOOK`, and
`RENDER_FRONTEND_DEPLOY_HOOK`. Services have automatic deploys disabled so
production deploys happen only after CI. Configure all Render environment
secrets directly in Render; never add production values to GitHub variables or
the repository. A blank deploy-hook secret is skipped, so populate every
service you want the workflow to deploy.

## k6 load matrix

Start the API and run `tests/load/run_matrix.ps1`. It exercises REST game
catalog reads and concurrent game WebSocket connections for 100, 250, 500,
750, and 1000 virtual users. Override the target using `-BaseUrl` and duration
using `-Duration`. Acceptance thresholds are REST p95 under 300 ms, observed
WebSocket event fan-out p95 under 500 ms, and request/WebSocket error rates
below 1%. Ensure test data and a representative engine event stream are active:
fan-out latency is measured from event timestamps, so no event samples means
that metric cannot establish the fan-out SLO.
