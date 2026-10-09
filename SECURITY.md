# Security controls

How each common risk is handled, and where. Tests: `backend/tests/api/test_security_access_control.py`
and `backend/tests/api/test_security_hardening.py`.

| Risk | Control |
|---|---|
| SQL injection | All queries go through SQLAlchemy with bound parameters; no string-built SQL. |
| Cross-site scripting | React escapes all output (no `dangerouslySetInnerHTML`). API responses carry `Content-Security-Policy: default-src 'none'`; the site (Vercel, `frontend/vercel.json`) has a strict CSP, `X-Frame-Options: DENY`, `nosniff`. |
| CSRF | API auth is a Bearer header. State-changing requests that carry cookies (refresh token, tracking cookies) must come from an allowed origin (`app/middleware/csrf.py`); cookies are HttpOnly, Secure, SameSite. |
| File uploads | Images (QR codes, PR materials, blog covers) are decoded and checked against their real file signature (PNG/JPEG/WebP/GIF), size-limited; SVG is refused (`app/security/uploads.py`). CSV imports are size-limited plain text. |
| Broken object level authorization | Every query is scoped to the user / partner from the token, never from the request body. An automated sweep calls every endpoint without a login and with a player token. |
| Rate limiting | Per-endpoint limits (login, sign-up, payments, partner actions) plus a per-IP ceiling for the whole API (`GLOBAL_RATE_LIMIT_PER_MINUTE`, writes separately). The client IP comes from the trusted proxy hop, so forged `X-Forwarded-For` values do not bypass it (`TRUSTED_PROXY_HOPS`). |
| JWT secrets | HMAC algorithms only (HS256/384/512, never `none`); production requires two different secrets of 32+ characters; library: PyJWT. |
| Keep the API server side | The frontend holds only public URLs; secrets live in the backend environment. |
| Password hashing | Argon2id; partner passwords are also checked against known breaches (HaveIBeenPwned k-anonymity). |
| Multi-factor authentication | Required for staff (admin, super admin, finance, support) in production; optional for players; partners do not use it by business decision. |
| CORS | Explicit https origins only (no wildcard), explicit methods and headers. |
| Tokens in browser storage | The access token is kept in memory; the refresh token is an HttpOnly cookie; the support "view as partner" token is memory-only. Nothing is in localStorage / sessionStorage. |
| Server-side permissions | Every admin / partner route enforces its permission on the server (`require_permission`, partner dependencies). |
| Row level security | PostgreSQL RLS is enabled on every table: only the owning application role can read rows; any other database role gets nothing (migration `d5f6a7b8c9d0`). |
| Webhook signatures | Payment webhooks and operator S2S ingest are HMAC-SHA256 signed with a timestamp (5-minute window), compared in constant time. |
| SSRF | Server-side requests to user / admin URLs (partner postbacks, tracking-domain checks) allow only public addresses on ports 80/443, no redirects (`app/security/ssrf.py`). |
| Source maps | Never built for production (`vite.config.ts`). |
| Default credentials | Seed accounts exist only outside production; in production a sign-in with any known seed password is refused until the password is reset. |
| Sensitive data in logs | A log processor redacts passwords, tokens, codes, PINs, payout details and bearer/JWT strings; production never logs email bodies. |
| Vulnerable dependencies | `pip-audit` and `npm audit` clean at the time of writing (python-jose replaced by PyJWT). |
