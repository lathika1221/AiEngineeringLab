# LATZ deployment runbook (career-portfolio demo)

Target: Cloudflare Pages (frontend) + Render Starter web service (API) + Neon Free (PostgreSQL) + Groq Free (AI).
Variable reference: `docs/ENVIRONMENT.md`. Render settings live in `render.yaml`.
This runbook describes steps; none of them has been run. Do each one deliberately.

**AI is switched off for the initial deployment.** `render.yaml` sets `AI_ENABLED` to false, so chat returns HTTP 503 until you deliberately enable it (see "Enabling AI later"). Everything else (login, conversations, projects, memories, history) works while AI is off.

## 0. Before anything else
1. All work is currently uncommitted. Render and Cloudflare build from Git, so the single approved commit must be made and pushed first (owner action).
2. Prices and limits change. Re-check the Render, Neon, Cloudflare and Groq pricing pages before creating accounts.
   Expected spend: about one Render Starter instance (about $7/month); everything else on free plans.
   If a dashboard shows any other charge, stop and re-check against the INR 1,000/month budget.
3. Decide the Pages project name now. Its address (`https://<name>.pages.dev`) is needed for `CORS_ORIGINS`.

## 1. Database (Neon)
1. Create a new Neon project in the region closest to the Render region in `render.yaml` (Singapore). Use a database that is **not** your development database.
2. Copy the connection string (it already ends in `?sslmode=require`). Keep it only for the Render environment.
3. Free plan facts to expect: compute sleeps after 5 idle minutes and the first request afterwards is slower; 1 GB storage cap per project.

## 2. Backend (Render)
1. In the Render dashboard create a Blueprint from this repository (`render.yaml`). Render asks for the variables marked `sync: false`:
   `DATABASE_URL`, `SECRET_KEY` (generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`), `GROQ_API_KEY`, `MODEL_NAME`, `CORS_ORIGINS`.
   `GROQ_API_KEY` is only required once AI is enabled (the startup check skips it while `AI_ENABLED` is false). If the dashboard insists on a value, check how it handles a blank entry; do not invent a key. `MODEL_NAME` must always be a real model name.
   All other variables (`ENVIRONMENT`, `DEBUG`, `PROJECT_NAME`, `VERSION`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REGISTRATION_ENABLED`, `AI_ENABLED`, `ENABLE_DOCS`, `AI_PROVIDER`, `PYTHON_VERSION`) come from `render.yaml`.
2. Leave `OPENAI_API_KEY` unset. `AI_PROVIDER` must stay `groq`: production startup fails for any other provider, and nothing falls back to another provider. Do not add a payment method to the Groq account (free tier only).
3. First deploy: the pre-deploy command `alembic upgrade head` applies the migrations (5 revisions, head `f7a2c9d1e3b6`, which adds the `ai_usage_daily` quota table and records that it created it), then the service starts.
   If the dashboard says pre-deploy commands are unavailable on your plan, run `alembic upgrade head` once from the service shell instead, before the first start.
4. Verify the two health endpoints (they answer different questions):
   - **Liveness, `GET <api>/health/`:** "the process is up". It never touches the database and returns 200 even if Neon is asleep or down. This is the Render health-check path (`healthCheckPath` in `render.yaml`). Keep the trailing slash: `/health` redirects.
   - **Readiness, `GET <api>/health/ready`:** "the database answers". It runs `SELECT 1` and returns `{"status":"ready","database":"ok"}` (200) or `{"status":"unavailable","database":"unreachable"}` (503). Use it for manual smoke tests only, not as the Render health check: Render calls the health check every few seconds, which would keep the Neon free-plan compute awake all day and use up its monthly compute allowance.
   - `/docs` must return 404.

## 3. Demo account (seed script, registration stays closed)
From the Render service shell (or any shell that has the same variables), type the credentials on the command line only:

    DEMO_USER_USERNAME=<name> DEMO_USER_EMAIL=<email> DEMO_USER_PASSWORD=<12+ chars> python -m scripts.seed_demo_user

- It prints only "created" or "already exists". Re-running is safe and never changes an existing password.
- Do not save the three DEMO_ variables as service environment variables.
- The account is an ordinary user; the app has no admin role.

## 4. Frontend (Cloudflare Pages)
Create a Pages project from the repository with:

| Setting | Value |
|---|---|
| Framework preset | Vite (React) or None |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Variable `VITE_API_URL` | the Render service origin, https, no trailing path |

`frontend/.node-version` pins Node 22 (Vite needs 20.19+ or 22.12+); set `NODE_VERSION=22` if the build reports an older Node.
`frontend/public/_redirects` makes deep links and refreshes work; `frontend/public/_headers` adds basic security headers.
After the first deploy confirm the Pages address equals what you put in `CORS_ORIGINS`; if not, update it on Render and redeploy the API.

## 5. Smoke tests (in this order)
1. Open the site, then refresh on `/projects` and on `/login`: no 404.
2. Browser dev tools, Network: API calls go to the Render origin, never `127.0.0.1`.
3. Sign in with the demo account.
4. `POST <api>/auth/register` returns 403 "Registration is currently closed."
5. **While AI is off (initial deployment):** `POST <api>/ai/chat` returns 503 "AI features are temporarily unavailable." Skip the chat test; the chat screen will show a generic request-failed message (known, see limitations).
   **Only after you have deliberately enabled AI (see below):** send one chat message; text streams in and finishes without an "incomplete" note.
6. Reload the page: you stay signed in and the conversation list loads. (With AI enabled, also confirm the chat history from step 5 is still there.)
7. `<api>/docs` returns 404; a request from a different origin is blocked by CORS.
8. Render logs show no stack traces and no secrets.

## 6. Rollback
- Frontend: Cloudflare Pages, Deployments, roll back to the previous production deployment.
- Backend: Render, Events or Deploys, redeploy the previous successful deploy. The migrations only add objects, so the previous code runs against the newer schema.
- Stop AI usage immediately: set `AI_ENABLED` to false (the API then returns 503 for chat only). Editing the variable in the Render dashboard is the quickest route; afterwards make `render.yaml` match in the next reviewed commit so a later Blueprint sync cannot switch it back on (confirm in the Render docs how a sync treats a dashboard edit).- Close the site to new logins: nothing to do, registration is already closed.
- Database downgrades (`alembic downgrade`) are guarded, but take a manual backup first and do it only deliberately.
  - *Migration ownership.* Each of the last three revisions records the objects it created as one JSON entry per revision in the comment on the `alembic_version` table, and its downgrade removes only what it recorded. For `f7a2c9d1e3b6`: a table it created and that is still empty is dropped together with its own record only; a table that has rows makes the downgrade refuse and change nothing; a table that already existed (for example built outside Alembic) is validated against the model, rejected if incompatible, left untouched and never claimed (validated: column types, nullability, primary key, the `(scope, usage_date)` unique key, `id` generated, server defaults `requests`/`tokens` = 0 and `updated_at` = `now()`; extra columns are accepted only if nullable or defaulted, so an extra NOT NULL column without a default is rejected because the quota INSERT would fail); a missing, malformed or untrusted record means the table is kept. Other revisions' records are never altered.

## 7. Enabling AI later (reviewed change)
Do this only when you want the chat to work. Quotas and rate limits are now enforced (section 8); review the defaults first.
1. In `render.yaml` change `AI_ENABLED` from `"false"` to `"true"` and commit it through the normal reviewed process. Never edit it straight on the server and forget Git.
2. In the Render dashboard make sure `GROQ_API_KEY` (your Groq key) and `MODEL_NAME` (a model your Groq account offers) are set. Startup refuses `AI_ENABLED=true` without the key.
3. Deploy manually (`autoDeployTrigger` is `"off"`). The pre-deploy migration step re-runs and does nothing new.
4. Run smoke test 5 (the chat test), then watch the Groq console for usage. The daily quotas (`AI_DAILY_*`, UTC) and the per-minute and stream limits are active as soon as AI is on; a rejected request is HTTP 429 with `Retry-After`, shown by the chat screen as a generic request-failed message.
5. To turn it off again, follow the rollback step above.

## 8. Known limitations (accepted for a career demo)
- While AI is off (and when a quota or rate limit rejects a request), the chat screen shows a generic "request failed" message instead of the server's explanation. Improving that message is a separate, not yet approved frontend change.
- The token is stored in browser localStorage and cannot be revoked before it expires.
- **Security limits (enforced, with limits).**
  - *Login:* `POST /auth/login` and `/auth/register` are limited per client address (`RATE_LIMIT_AUTH_PER_MINUTE`); over the limit is HTTP 429 with `Retry-After`. The limit is per address, not per account, so a distributed attack from many addresses is not stopped, and an attacker can lock out everyone who shares their address.
  - *Client address (OPEN on Render, blocks public login exposure there; for Railway see section 9):* `render.yaml` keeps `TRUSTED_PROXY_COUNT=0`, so all visitors behind Render's proxy share one login bucket: more than `RATE_LIMIT_AUTH_PER_MINUTE` logins a minute from anyone block everyone briefly (the safe failure direction; it cannot be bypassed by forging headers). Render's documentation says the real client address is read from `X-Forwarded-For` but does not state the number of hops it appends or that earlier entries are sanitised, and the third-party examples found disagree with a fixed value, so the count is NOT verified and has not been changed. Before exposing login to the public, measure the real header from a Render deployment of this service (see `docs/ENVIRONMENT.md`) and only then set the count; until then treat login rate limiting as shared-bucket only.
  - *AI quotas:* daily request limits (per user and global) are exact and stored in the database, atomic under concurrency. The global token limit is approximate and NOT a strict hard cap: tokens are reserved up front, then replaced by the measured value, which can be larger (tool rounds, long prompts), so a burst of in-flight requests can overshoot it. There is no per-user token quota. Measured tokens are the provider's number when reported, otherwise `ceil(characters/4)` of prompt plus output, an approximation that can be wrong by a wide margin and can under-count tool-calling rounds. If a settlement or refund is definitely rejected by the database, the reservation stays counted (an over-count, not a bypass), the call is retried once more at the end of the request, and a log line records the failure without request data. **Settlement is not exactly-once:** if the database commits but the acknowledgement is lost, the application sees an error it cannot distinguish from a failure, and the retry can apply the same adjustment a second time (a settle can under-count by up to the reserved-minus-actual tokens; a release can refund twice). Preventing that needs a durable per-reservation idempotency record, which is not implemented. The window is a lost connection at the instant of COMMIT; the daily counters reset at 00:00 UTC.
  - *In-memory parts:* per-minute limits and the concurrent-stream cap live in one process, reset on restart or redeploy, and are not shared across instances or workers. They suit the single Render instance with one uvicorn worker used here. Scaling out needs shared storage, which is not implemented.
  - *Streams:* a stream slot is freed on completion, error, cancellation and disconnect. The slot is leased: every streamed chunk renews a 5-minute idle lease, so a long stream that keeps producing output keeps its slot, and no stream may hold a slot longer than 10 minutes in total (it is ended with a "timeout" marker). A stream that is silent for more than 5 minutes (a hung provider call) is treated as dead, its slot can be reused, and it is stopped if it wakes up; for that one stalled stream the cap of `AI_MAX_CONCURRENT_STREAMS` is therefore not guaranteed. A client that disconnects before the first byte may leave one request counted against its quota.
  - *Errors:* chat failures return a generic HTTP 502 and logs keep only the error class and status, never provider messages, keys or addresses.
- No Content-Security-Policy yet (Google Fonts and an inline theme script need hashes or self-hosting first).
- Cloudflare preview deployments use other addresses and would be blocked by CORS.
- The first request after Neon sleeps, and any request during a Render deploy, can be slow or fail briefly.

## 9. Railway: client address for login rate limiting
The runbook above targets Render and is unchanged. This section covers only how the API finds the client address when it runs on Railway behind Railway's public HTTP edge. It does not describe creating the Railway service.

**Setting.** `TRUSTED_CLIENT_IP_HEADER=x-real-ip` (empty by default, so nothing changes unless it is set). `TRUSTED_PROXY_COUNT` stays 0 (or unset) on Railway: production startup rejects the two together, and `X-Forwarded-For` is not used.

**Why `X-Real-IP` and not `X-Forwarded-For`.** What Railway has stated (staff answers on Railway's community help site and its public-networking specs page; vendor statements, not independently verified):
- the public edge overwrites `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` on every request, including copies the caller sends, and `X-Real-IP` is the header to use for rate limiting;
- Railway publishes no edge address range and no signed header, so the app cannot check that a request really came through the edge;
- requests over `*.railway.internal` skip the edge, so any other service in the same environment can send whatever `X-Real-IP` it likes;
- staff answers about whether `X-Forwarded-For` is stripped or appended to have disagreed, so a hop count built on it would rest on an unclear contract.

**Conditions that must hold while the setting is on (an architecture rule, not something the code can enforce).**
1. The API is the only service in its Railway project environment. Adding a second service, a worker, a cron service or a Railway sandbox to that environment lets it reach the API over the private network with a forged `X-Real-IP`.
2. No TCP proxy is enabled for the API (it would also bypass the HTTP edge).
3. No other proxy or CDN sits in front of the Railway domain. A CDN in front (for example Cloudflare on a custom domain) makes `X-Real-IP` carry the CDN's address, so every visitor lands in one bucket. There are community reports of `X-Real-IP` showing an edge or CDN address on Railway; that fails safe (shared bucket) but defeats per-client limiting.
4. If any of these changes, set `TRUSTED_CLIENT_IP_HEADER` back to empty and re-review before turning it on again.

**Do not configure `FORWARDED_ALLOW_IPS` (or `--forwarded-allow-ips`) to trust arbitrary proxy addresses.** Uvicorn has its own proxy-header handling, on by default, that is separate from this setting. It trusts only `127.0.0.1` unless told otherwise, and for a trusted peer it replaces the socket address (`request.client.host`) with an address taken from `X-Forwarded-For`. `get_client_ip()` never reads `X-Forwarded-For`, but its fallback is that socket address, so widening the trusted list (for example `*` or a broad address range) would let a forged `X-Forwarded-For` choose the fallback bucket. This was reproduced locally: a forged `X-Forwarded-For` from a trusted peer changed the address the app saw, and did not when proxy headers were off or the peer was not trusted. Leave `FORWARDED_ALLOW_IPS` unset on Railway. Requests made from inside the container itself (for example from the Railway Console) come from `127.0.0.1`, the default trusted peer, so they are not a model of public traffic.

**Failure direction.** A bad, missing or repeated header falls back to the peer address, which on Railway is the edge, so all such requests share one bucket (more than `RATE_LIMIT_AUTH_PER_MINUTE` logins a minute from anyone block everyone briefly). The limiter is in process memory: it resets on every restart, redeploy or sleep (Railway Serverless).

**NOT yet verified on a running Railway deployment (do this before public login exposure).**
- That a client-supplied `X-Real-IP` is overwritten on the public path, and that a real client's address arrives in it rather than an edge address.
- Verify without any code change or database write: from several networks, send repeated failed logins to the public domain (a nonexistent username returns 401 and writes nothing), each time with a different forged `X-Real-IP`. If the edge overwrites the header, the request after the limit gets HTTP 429 from one network and clients on other networks are unaffected; if forged values never trigger 429, the header is not overwritten and the setting must stay off.
- That `X-Real-IP` is the real client's address and not an edge address: confirm that two different networks do not share one bucket.
