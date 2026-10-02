# Real-time games

## Setup, run, test, deploy

For a local setup, copy `.env.example` to `.env`, install
`requirements-dev.txt`, start PostgreSQL/Redis with `docker compose up -d`, and
apply migrations with `alembic upgrade head`. Start the API using
`uvicorn app.main:app --reload` and the game engine using
`python -m app.games.base.engine`. Run tests with `python -m pytest -q`.

The multi-stage, non-root container and Render services are defined in
`Dockerfile` and `render.yaml`. Production secrets, database backups, release
migrations, and the k6 acceptance matrix are documented in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Local development quick start

With PostgreSQL + Redis running (`docker compose up -d postgres redis`) and
migrations applied, `uvicorn app.main:app --reload --port 8000` is all you
need outside production:

- Aviator, Color Prediction and the simulated Cricket feed run **inside the API
  process** (`RUN_GAME_ENGINES`, auto-on outside production; Redis leader
  election keeps it to one runner). Production keeps using the separate
  `python -m app.games.base.engine` worker.
- Roles, games and these local accounts are seeded on startup
  (`SEED_DEFAULT_ACCOUNTS`, never in production). Sign in with the username:

  | Role | Username | Password |
  |---|---|---|
  | Super admin | `superadmin` | `SuperAdmin@123` |
  | Admin | `admin` | `Admin@12345` |
  | Support | `support` | `Support@123` |
  | Auditor | `auditor` | `Auditor@123` |
  | Player | `player` | `Player@123` |

- Admin 2FA is only enforced in production (`ADMIN_2FA_REQUIRED` overrides).
- **Color Prediction = WinGo** (`wingo_30s`, `wingo_1m`, `wingo_3m`, `wingo_5m`):
  number 0-9 per period; Green/Red 2x (1.5x on 5/0), Violet 4.5x, number 9x,
  Big/Small 1.96x. The legacy `color` engine is retired.
- **Cricket**: set `CRICAPI_KEY` (free at cricketdata.org) for every real match
  worldwide, grouped as International / T20 Leagues / Domestic / Women. Without
  a key a simulated Virtual League runs.
- **Simulated players** (`SIMULATED_PLAYERS`, auto-on outside production): ~40
  bot accounts that place real virtual-credit bets so live feeds and the
  leaderboard (refreshed every minute) have activity.
- Players register with just a username and password (email is optional) and
  sign in with their username (or email).

## Super admin panel

- **Staff**: create, edit (email/role/password), block/unblock, remove (demote +
  disable, history kept), per-admin activity, and *demo credits* for testing.
- **Roles & permissions**: custom roles with any permission set (`/admin/roles`).
- **Platform settings** (`/admin/system-settings`): name, logo, maintenance mode
  (blocks player bets, banner site-wide), sign-up/daily bonus, entry limits and
  WinGo reward multipliers. Public read-only subset at `/system/config`.
- **Audit logs**: search (admin, action, target, IP) + type and date filters.
- **Live risk monitor** (`/admin/risk/live`): stakes and exposure per Aviator
  round, WinGo period (payout if each number is drawn) and Mines session, with
  pause/resume and *void & refund*. Results are provably fair and are never
  steered by stakes.
- **Credit flow** (`/admin/finance/overview`, super admin only): wagered, paid,
  house result per game and ledger movements. Virtual credits only — no real
  deposits, withdrawals or payment gateways.

## Super-admin login provisioning

Account passwords are stored as Argon2 hashes and cannot be read back from the
database. To create a super-admin or reset an existing account, run this from
the backend directory. The password is entered interactively and is not placed
in shell history or process arguments:

```powershell
python -m scripts.create_super_admin --username YOUR_USERNAME --email YOUR_EMAIL
```

The script prompts for a new password twice and requires 12-128 characters.
It prints the configured username after success; use that username/email and
the password you entered to log in. Enable admin 2FA after signing in. Do not
reuse example or development passwords in production.

If the administrator lost access to the enrolled authenticator, add
`--reset-authenticator` to that command. It rotates the 2FA secret, enables the
new authenticator, and prints a one-time `otpauth://` provisioning URI in the
Render Shell. Import that URI into an authenticator app immediately; it is
secret and should not be pasted into chat or logs. This operation also resets
the account password through the interactive prompt.

## Aviator

Place a bet or cash out through `POST /api/v1/games/aviator/action`. Every
request must include an `Idempotency-Key` header. Bet requests use
`{"action":"bet","round_id":"...","amount":100,"auto_cashout":2.0}` and
cashout requests use `{"action":"cashout","round_id":"...","entry_id":"..."}`.
The server derives the cashout multiplier from the round start timestamp; client
multiplier values are not accepted.

Connect to `/ws/games/aviator` for `round_open`, anonymized `bet_placed`,
`cashout`, `crash`, and `round_settled` events. `round_open` supplies the
round's start timestamp and growth parameters once so clients can animate
locally. The server seed commitment is published before betting opens and the
seed is revealed after the crash.

## Color Prediction

Place a bet through `POST /api/v1/games/color/action` with an
`Idempotency-Key` header and a JSON body containing `round_id`, `amount`, and
`colour` (`RED`, `GREEN`, or `VIOLET`). The WebSocket channel is
`/ws/games/color`.

The game settings JSON supports `timer_length_seconds`,
`lock_before_end_seconds`, and `payout_multipliers` (for example,
`{"RED":2,"GREEN":2,"VIOLET":4.5}`). The betting deadline and result time are
calculated by the server. Round results are derived from the provably-fair
seed and the server seed is revealed with the result.

Both games can be enabled or disabled with
`PATCH /api/v1/admin/games/{game_id}/settings` using `{"is_active":false}`.
Disabling a game prevents new rounds and bets; active Aviator rounds can still
be cashed out and settled.

## Celery workers

Celery workers and Beat use `REDIS_URL` for the broker and result backend and
`DATABASE_URL` for worker database access. Start the backend services from this
directory with `docker compose up -d postgres redis`, then run the worker and
Beat scheduler in separate terminals:

```powershell
celery -A app.workers.celery_app:celery_app worker --loglevel=INFO
celery -A app.workers.celery_app:celery_app beat --loglevel=INFO
```

On Windows, use Celery's single-process pool for the worker:

```powershell
celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

Beat runs nightly wallet reconciliation at 02:00 UTC, expired-token cleanup at
03:30 UTC, and archival of terminal game rounds and entries older than 90 days
at 04:00 UTC. Leaderboards refresh every 15 minutes.