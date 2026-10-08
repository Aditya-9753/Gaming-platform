# Partner / affiliate platform

Partners send traffic to Rudra247 through tracking links and earn CPA and/or revenue share
on the players they bring. Product spec: "Partner / Affiliate Platform — PRD + ERD (Final)", 8 Oct 2026.

```
partner -> source -> tracking link (?ref=CODE / /r/CODE, sub1..sub5)
  -> click (click_id, aff_click cookie) -> redirect to the product with click_id
  -> registration / deposit / daily revenue (signed S2S, or the internal Rudra247 bridge)
  -> commission (CPA on qualified FTD, revshare on NGR) -> wallet ledger
  -> settlement period close (pending -> available, carryover) -> withdrawal -> paid
```

## Where things live

| Part | Path |
|---|---|
| Tables (`aff_*`, 43) | `app/models/affiliate.py`, migration `alembic/versions/c4e5f6a7b8c9_affiliate_platform.py` |
| Services | `app/affiliate/` — `partners`, `tracking`, `ingest`, `commission`, `settlement`, `ledger`, `withdrawals`, `analytics`, `stats`, `risk`, `postbacks`, `security`, `operator_bridge`, `jobs` |
| API | `app/api/v1/affiliate/` — partner portal `/api/v1/aff/*`, back office `/api/v1/aff/admin/*`, ingest `/api/v1/ingest/*`, public `/r/{code}` and `/?ref=` |
| Celery tasks | `app/workers/tasks_affiliate.py` (scheduled in `celery_app.py`) |
| Partner portal | `frontend/src/pages/partner/` at `/partner/*` |
| Back office | `frontend/src/pages/admin/affiliate/` at `/admin/affiliate/*` |
| Tests | `tests/api/test_affiliate_platform.py` |

Reused platform tables: `users` (partners are users with role `PARTNER`), `roles`, `permissions`,
`role_permissions`, `refresh_tokens` (sessions), `audit_logs`, `notifications`, `system_settings`
(global affiliate settings are stored as `aff.<key>`). Money is `NUMERIC(19,4)` in USD.

## Roles

`SUPER_ADMIN`, `ADMIN`, `FINANCE_ADMIN` (new), `SUPPORT`, `PARTNER` (new). A subpartner is a
`PARTNER` whose `parent_partner_id` is set. Permissions are the `aff:*` codes in
`app/core/constants.py`. Staff roles need 2FA when `ADMIN_2FA_REQUIRED` is on (always in production).
Partners do **not** use 2FA (business decision, 8 Oct 2026): payouts are protected by the 24-hour
cool-down on new or changed payout methods, security notifications, and the finance review queue.

## Configuration

| Env var | Meaning |
|---|---|
| `AFFILIATE_INGEST_SECRET` | HMAC secret for `/api/v1/ingest/*` (required to accept S2S events) |
| `AFFILIATE_INGEST_IPS` | Optional IP allow-list for ingest |
| `AFFILIATE_INTERNAL_OPERATOR` | `true`: Rudra247 reports its own referred players (default) |
| `AFFILIATE_PUBLIC_BASE_URL` | Main site URL used for links until a tracking domain exists |
| `AFFILIATE_IP_SALT` | Salt for visitor IP hashes (required in production) |
| `AFFILIATE_FX_AUTO_FETCH` | Fetch ECB reference rates daily (default on) |
| `AFFILIATE_BREACH_CHECK` | Reject partner passwords found in breaches via HaveIBeenPwned (default on) |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Sign-in captcha after 5 failures, lock after 10 (all logins) |

Everything else (min payout, hold days, cookie days, settlement period type, subpartner share,
app download links, languages, fallback FX rates, auto-approve, …) is in
**Admin → Affiliate Settings** and audited.

**Tracking domain.** No domain is hard-coded. The super admin adds the production domain (and
mirrors) in **Admin → Tracking Domains**; every partner link switches to the primary active
domain without new codes. Links: `https://{domain}/?ref={code}` and `https://{domain}/r/{code}`.
`/?ref=` works on the main site (the frontend logs the click through `POST /api/v1/aff/track/click`)
and on the API domain; `/r/{code}` is served by the API.

## Operator S2S API

Every request: JSON body, headers `X-Timestamp: <unix seconds>` and
`X-Signature: hex(HMAC_SHA256(secret, "<timestamp>.<raw body>"))`. Older than 5 minutes is
rejected. New event → `201`, duplicate → `200` with the first record. Amounts are converted to
USD at ingest with the European Central Bank reference rate of that day (or the latest before it),
fetched automatically twice a day; currencies the ECB does not publish (e.g. BDT, PKR, NGN) are
entered by finance in Admin → Deals & Plans → FX rates. A missing rate leaves the event FAILED and
it is retried once a rate exists.

| Endpoint | Body | Idempotency |
|---|---|---|
| `POST /api/v1/ingest/registration` | `external_customer_id`, `click_id` or `promo_code`, `country`, `registered_at`, optional `sub1..sub5` | `external_customer_id` |
| `POST /api/v1/ingest/deposit` | `external_customer_id`, `external_transaction_id`, `amount`, `currency`, `status` (`PENDING`/`COMPLETED`/`FAILED`), `completed_at` | transaction id + status |
| `POST /api/v1/ingest/revenue` | `{"rows": [{external_customer_id, date, bets, wins, bonuses, fees, chargebacks, ngr?, currency}]}` (≤ 5000 rows) | body hash; rows upsert per (customer, date) until the period closes |
| `POST /api/v1/ingest/reversal` | `external_reversal_id`, `external_transaction_id`, `amount`, `reason` | `external_reversal_id` |

If `ngr` is omitted it is `bets − wins − bonuses − fees − chargebacks`. Events are stored raw
first; failures are visible and retryable in **Admin → Ingest Monitor** (automatic retry up to
8 times). If the operator cannot push, upload the same columns as CSV there.

Python signing example:

```python
raw = json.dumps(body).encode(); ts = str(int(time.time()))
sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
requests.post(url, data=raw, headers={"X-Timestamp": ts, "X-Signature": sig, "Content-Type": "application/json"})
```

**Rudra247 itself** (`AFFILIATE_INTERNAL_OPERATOR=true`): a player who signs up with a click id
(from the link redirect, the `aff_click` cookie or `?click_id=`) or a promo code is reported in the
same database transaction (outbox in `aff_ingest_events`, source `INTERNAL`); credited and reversed
deposits of those players too; daily NGR (bets − payouts − bonuses, INR) is reported hourly for
today and yesterday.

## Background jobs

| Job | Schedule (Celery beat) |
|---|---|
| process outbox / retry failed ingest | 15 s |
| commission for changed revenue | 60 s |
| analytics rollups (dirty partners + today) | 120 s |
| partner postbacks | 30 s |
| click backlog (clicks queued when the DB was slow) | 60 s |
| internal Rudra247 revenue | hourly |
| ensure current period / optional auto-close | hourly |
| ECB FX reference rates | 15:30 and 21:30 UTC |
| ledger reconciliation (risk event on mismatch) | 02:15 UTC |
| next months' click partitions (PostgreSQL) | 01:20 UTC |

In development (`RUN_GAME_ENGINES` on) the same jobs run inside the API process, so one
`uvicorn` command runs everything.

## Settlement

Finance closes a period in **Admin → Settlement Periods** (only the super admin can close an
unfinished period or reopen one). Close = tier rates → settle pending (+ CPA whose hold ended)
to available → subpartner share for masters (never negative) → carryover policy (off: write off
to 0; cap: write off beyond the cap) → statements → auto-withdrawals.

## Open questions from the PRD (defaults used until the business decides)

| Question | Default in code |
|---|---|
| Production tracking domain(s) | none; links use `AFFILIATE_PUBLIC_BASE_URL` until added |
| Exact NGR formula | bets − wins − bonuses − fees − chargebacks, or the operator's `ngr` |
| Negative carryover | on (per deal; cap optional) |
| Period length / min payout | weekly / 20 $ (settings) |
| Subpartner share / depth | 5 % / 1 level (settings, per partner) |
| Attribution | promo code wins, else last click within 30 days |
| Payout methods | e-wallet email, USDT TRC20, bank, UPI, other; finance pays manually and marks paid |
| Star icon in the header | shows the partner's current deal |
| Partner terms | none published; publish v1 in Affiliate Settings after legal review |
| Captcha after 5 failed logins | Cloudflare Turnstile once its two keys are set; until then lock after 5 failures |
| Partner 2FA | removed on request; staff keep 2FA |
