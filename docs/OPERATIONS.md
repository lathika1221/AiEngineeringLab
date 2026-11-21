# LATZ operations: capacity, security posture, backup/recovery, rollback

Scope: the controlled-beta production stack (Cloudflare Pages frontend, Railway backend,
Neon PostgreSQL, Groq). Everything below states what was **verified** and what is **not**.
Nothing here changes a production setting; it is the reference for deciding to.

## 1. Capacity and cost

**Hard limits in the code (defaults; production overrides are Railway variables):**

| Limit | Default | Scope | Effect when hit |
|---|---|---|---|
| `AI_DAILY_REQUESTS_PER_USER` | 10 | per account per UTC day | HTTP 429 + `Retry-After` |
| `AI_DAILY_REQUESTS_GLOBAL` | 80 | all users per UTC day | HTTP 429 |
| `AI_DAILY_TOKENS_GLOBAL` | 150,000 | all users per UTC day (reserved up front, settled on measured usage) | HTTP 429 |
| `RATE_LIMIT_AI_PER_MINUTE` | 10 | per account | HTTP 429 |
| `AI_MAX_CONCURRENT_STREAMS` | 3 | whole process | HTTP 429 before any provider call |
| `AI_MAX_CONCURRENT_STREAMS_PER_USER` | 1 | per account | HTTP 429 "You already have an AI response in progress"; one user can never take more than one of the 3 slots |
| `RATE_LIMIT_AUTH_PER_MINUTE` | 10 | per client address, login and register counted separately | HTTP 429 |
| Stream lease | 300 s idle, 600 s absolute | per stream | stream ends with a `timeout` marker |
| DB pool | 5 + 5 overflow | per process | queueing up to `DB_POOL_TIMEOUT` (30 s) |

**What this means for a beta (arithmetic from the limits above, not a measurement):**
- The global daily request cap (80) is saturated by 8 users each using their full 10 requests. Beta size is therefore bounded by that cap, not by servers. Raising it is a deliberate decision with a cost attached (below), never a silent change.
- The per-minute limiter, stream cap and login limiter live in process memory. They reset on every restart, redeploy or Railway Serverless sleep, and are not shared between instances. This is correct for the current single replica and **wrong** the moment a second replica exists.
- One replica, 1 GB / 2 vCPU (Railway plan limits as shown in the dashboard).

**Cost: not assessed.** Groq pricing and rate limits were deliberately not looked up or assumed. Before raising any quota, read the current Groq console limits and pricing for `openai/gpt-oss-20b` and multiply by `AI_DAILY_TOKENS_GLOBAL`. The Railway trial/credit balance shown in the dashboard ("30 days or $5.00 left") means hosting itself has an expiry to plan around. Neon plan limits and retention were also not verified.

## 2. Security posture (verified unless marked)

| Control | State | Evidence |
|---|---|---|
| Public registration | closed (`REGISTRATION_ENABLED=false`, production fails closed) | startup log `registration=closed`; tests |
| Cross-account isolation | enforced per query on every route | `tests/test_multiuser_isolation.py` (two real logins, 36 cases incl. AI context) |
| Unauthenticated AI | none: every AI route needs a token | isolation tests, 401 on all |
| Client IP for limits | `TRUSTED_CLIENT_IP_HEADER=x-real-ip` | forged-header test on production: 10 x 401 then 429; a new forged value stayed 429 |
| Two-network bucket independence | **not yet verified on production** | pending hotspot test |
| Secrets in logs/responses | none observed; provider errors are generic | `tests/test_ai_quota.py` (secret-leak cases) |
| CSP | report-only, **not enforced** | `frontend/public/_headers`, `tests/csp.test.ts` |
| Token storage | JWT in `localStorage`, ~60 min expiry, logout clears client only | by design; XSS would expose it, which is why CSP matters |
| Password change | `POST /auth/change-password` (API only, no UI yet): re-checks the current password, rejects reuse, applies the 12 to 72 byte policy, returns a fresh token and invalidates every older one (tokens carry a keyed fingerprint of the password hash) | `tests/test_account_lifecycle.py` |
| Account deletion | `POST /users/me/delete` (API only, no UI yet): password re-check, deletes the account, everything it owns and its quota counters; other accounts untouched | same file, incl. real PostgreSQL FK cascade |
| Preview deployments | public, noindex header only | access policy is a dashboard setting, not applied |

**Architecture rule for `x-real-ip` trust (must stay true):** the API is the only service in its Railway environment, no TCP proxy, no CDN/custom domain in front of it. If any changes, clear `TRUSTED_CLIENT_IP_HEADER` and re-review (`docs/DEPLOYMENT.md` section 9).

## 3. Public-launch gates (registration stays closed until all pass and the owner approves)

Blocking (missing today): a UI for password change and account deletion (the endpoints exist), password recovery and email verification (both need an email provider and a decision on one), data export, logout that revokes the current token (a password change now revokes all of them), per-account login throttling (a caller rotating addresses is only slowed by bcrypt and the 12 to 72 byte policy; characterized in `tests/test_account_rate_limits.py`), CSP promoted from report-only to enforcing after a clean observation pass, restricted preview deployments, a reviewed Groq cost ceiling, and a production-hosting plan beyond the trial credit.
Non-blocking improvements: shared (Redis or DB) limiter before a second replica, error monitoring/alerting, an uptime check on `/health/ready`.

## 4. Backup and recovery

**What exists:** the database is Neon PostgreSQL (project `ael-production`). Neon provides point-in-time history and branching; the **retention window depends on the plan and was not verified**. Check it in the Neon console before relying on it.

**Logical backup (works on any plan, read-only against production):**
```
pg_dump "$DATABASE_URL" -Fc -f latz-$(date +%F).dump     # run from a trusted machine; never paste the URL into chat or logs
```
Store the file encrypted and off the machine; it contains user data and password hashes.

**Restore: always into a NEW empty database or Neon branch, never over production:**
```
createdb latz_restore            # or create a Neon branch / new database
pg_restore -d latz_restore --no-owner --exit-on-error latz-YYYY-MM-DD.dump
DATABASE_URL=<restore url> alembic current        # expect the production head (f7a2c9d1e3b6)
```
Verify row counts per table against the source, then point a *non-production* backend at it for a login/chat smoke test. Promote only by an explicit, reviewed switch of `DATABASE_URL`.

**Rehearsal evidence (synthetic data, local disposable PostgreSQL 16, not Neon):** schema built with `alembic upgrade head` to `f7a2c9d1e3b6`, 2 users and 2 memories dumped with `pg_dump -Fc`, restored with `pg_restore --exit-on-error` into a fresh database: exit 0, identical counts (users 2, memories 2), `alembic current` = head. Restore of production data on Neon was **not** performed.

## 5. Rollback

Known-good reference: backend and frontend commit `5f7294c` (Pages deployment `b49b0ef1-f8df-4402-aa71-4ba1735aa251`, Railway deployment `654edd2b` after the IP-header change).

| Change | Rollback |
|---|---|
| `TRUSTED_CLIENT_IP_HEADER` | Variables, delete or empty it, Deploy Changes. Startup log must show `registration=closed`. |
| AI problems (cost, abuse, provider outage) | Set `AI_ENABLED=false` and deploy: chat returns 503 "AI features are temporarily unavailable." and nothing else is affected. |
| Bad backend release | Railway Auto Deploy is **off**: deploy the previous commit deliberately (`5f7294c`) from the service's Deployments tab, then verify `/health/ready` and the startup flags. Older Railway deployments show as REMOVED; whether one can be redeployed was not tested, so rely on redeploying the commit. |
| Bad frontend release | Cloudflare Pages, Deployments, pick the last good deployment, "Rollback to this deployment" (instant; no rebuild). |
| Bad migration | Migrations are additive and guarded (`tests/test_migrations.py`, 225 Postgres-backed cases). Take a `pg_dump` first; restore into a new database rather than downgrading in place. |
| Secrets | Rotate in the provider console, then update the Railway variable and deploy. Never in chat or the repo. |

## 6. Verification checklist after any production change
1. Startup log: `environment=production docs=off ... registration=closed ai=on` (or `ai=off` if intended).
2. `GET /health/ready` returns 200 `{"status":"ready","database":"ok"}`.
3. Sign in at the Pages URL; open a conversation. Send one chat only if the change touches AI (10 per user per day).
4. Browser console on the frontend: no new errors; CSP report-only messages reviewed.
