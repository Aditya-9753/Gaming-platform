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
- **Risk controls** (`/admin/risk/controls`, super admin only): a dedicated
  ON/OFF switch per game family (WinGo / Aviator / Mines). ON enforces strict
  exposure ceilings — a whole-round stake cap and a per-player round stake cap
  — so the house's worst-case liability stays bounded. A read-only **yield
  backtest** (`/admin/risk/backtest`) replays settled bets and reports the hold
  actually achieved per game against the configured target. The switch changes
  *what stakes are accepted*, never a round result — outcomes stay provably
  fair and are never steered.
- **Credit flow** (`/admin/finance/overview`, super admin only): wagered, paid,
  house result per game and ledger movements.
- **Payments** (`/admin/payments`): deposits, withdrawals, bank credits and
  UPI QR collection accounts — see below.

## Payments (deposits and withdrawals)

Implements the *Payment & Wallet Security Architecture v2*: deposit status is
set by the system from bank evidence, withdrawal completion only by the super
admin. Code: `app/services/payment_service.py`, APIs in `app/api/v1/payments/`.

**Deposit** (`/payments` page for players):
1. The player picks an amount; the server creates an intent with a unique
   reference (`RD…`), an expiry, and a random 1-99 paise added to the amount,
   routed to an approved staff QR account (least-loaded, within its limits).
   The page shows a UPI QR with amount + reference pre-filled.
2. The player pays and may enter the UTR — a lookup hint, never proof.
3. The deposit becomes **SUCCESS** only when a *bank credit* is matched to it:
   a signed provider webhook, a bank-statement line imported by the account
   owner, or the owner confirming the credit they can see in their own bank
   (manual check, step-up code, UTR mandatory and globally unique). Matching
   is by reference in the remark, then the player's UTR, then the unique amount.
   Amount or account mismatches go to manual review instead of crediting.
4. Unpaid intents expire (**REJECTED**); bank chargebacks reverse a deposit
   and freeze the wallet if the money was already spent.

**Withdrawal**: the player sets a transaction PIN, adds a payout account
(bank or UPI, encrypted at rest, usable after a cooling period) and requests a
withdrawal. The amount moves from `balance` to `pending_withdrawal`
immediately (WITHDRAWAL_HOLD). Risk flags (first withdrawal, new or shared
payout account, deposit-then-withdraw, velocity, bonus-heavy) are shown to
reviewers. Only the **super admin** completes it (step-up code + unique bank
payout UTR, WITHDRAWAL_SETTLE) or rejects it (funds returned,
WITHDRAWAL_RELEASE). Above `withdrawal_high_value_paise` another admin must
first mark "payout initiated" (maker-checker). The player can cancel while it
awaits approval.

**Roles**: super admin, auditor and support see everything; an admin adds
their own QR (live after super-admin approval; changing the UPI id sends it
back for approval) and sees/acts on deposits paid into it; admins see the
withdrawal queue with masked payout details. Full bank details are shown to
the super admin only, and every view is audited.

**Controls**: idempotency keys on deposit and withdrawal requests, row locks
plus a version column (optimistic lock) on every state change, a transition
table with a `payment_status_history` row per change, audit-log entries for
staff actions, rate limits on UTR/PIN/withdrawal endpoints, and an integrity
check (`/admin/payments/integrity`). Limits live in platform settings and are
editable on the admin Payments page.

**Provider webhook**: `POST /api/v1/payments/webhook/{provider}` with
`X-Webhook-Timestamp` and `X-Webhook-Signature` = hex HMAC-SHA256(secret,
`"{timestamp}." + body`); configure `PAYMENT_WEBHOOK_SECRETS`. Event types:
`payment.credit` (utr, amount_paise, reference/remark, account_vpa),
`payment.failed` (reference), `payment.reversed` (utr). Replays are ignored.

Before handling real money, confirm the payment provider's terms and the
KYC/AML, payments and gaming rules that apply where you operate.

## Fairness architecture (outcomes are independent of operators)

```
round created ──► serverSeed = random 32 bytes (never sent anywhere)
                  commitment = SHA-256(serverSeed) ──► published in round_open
                  clientSeed (public) + nonce = round number
betting closes
result = HMAC-SHA256(serverSeed, "clientSeed:nonce") → WinGo n = floor(r·10), Aviator crash point
round finished ──► serverSeed revealed → anyone re-hashes it and recomputes the result
```

- `app/games/fairness_guard.py` is the only gate for round secrets: the seed is
  returned **only after the round is finished** (public, admin and super admin
  APIs alike), and hidden game state such as a live Mines layout is stripped.
- There is no endpoint, flag or test mode to read an outcome early or set one.
- The Exposure Monitor (`/admin/risk/live`, super admin only) is read-only:
  `GROUP BY pick` totals plus a display-only "house P/L if this number is
  drawn" column. Its only controls are pause/resume and void-and-refund of a
  whole round (all stakes returned, audit logged) — neither touches the RNG.
- Players verify on `/fairness`, either through the API or entirely in the
  browser (WebCrypto re-implementation, cross-checked against the Python code).

## Security & Fairness page (`/admin/security`, super admin only)

- **Hold Analyzer**: actual hold per game from settled bets vs the hold the
  payout table / house edge predicts, with an approximate 95% range. The
  what-if simulator replays the engines' own provably-fair functions with a
  fresh random seed (returned, so runs are reproducible); it never touches a
  live round. Margin is set only through payouts / house edge for everyone.
- **Ledger integrity**: every `wallet_transactions` and `audit_logs` row is
  sealed with AES-256-GCM (row id as associated data) when
  `AUDIT_ENCRYPTION_KEY` (64 hex chars) is set. "Verify" flags rows edited
  outside the app.
- **Seed rotation**: rotate the public client seed used by new rounds; old
  values stay listed so finished rounds remain verifiable.

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