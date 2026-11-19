# Production environment variables (names and descriptions only)

This file lists every variable the deployed LATZ stack reads. It never contains values.
Set values in the hosting dashboards (Render, Cloudflare Pages), never in Git.
For local development use `.env.example` instead (placeholders, never commit a real `.env`).
Backend names come from `src/config/settings.py`; the frontend name from `frontend/src/shared/api/client.ts`.

Where to set: **Render** = web service Environment (`render.yaml` pre-fills the non-secret ones; the five secret or site-specific ones, `DATABASE_URL`, `SECRET_KEY`, `GROQ_API_KEY`, `MODEL_NAME` and `CORS_ORIGINS`, are entered in the dashboard).
**Pages** = Cloudflare Pages project, build variables.

## Backend (Render)

**Settings with no default (the app refuses to start if any is missing):** `PROJECT_NAME`, `VERSION`, `DATABASE_URL`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `AI_PROVIDER`, `MODEL_NAME` and `SECRET_KEY`.
Six of them only need a value. `SECRET_KEY` is stricter: besides being required, its value is validated in every environment. It must contain at least 32 non-whitespace characters and must not be a placeholder (for example `change-me`, or anything starting with `replace-with`), so it has to be a genuine random value set explicitly for production.

| Variable | Required | Secret | Description |
|---|---|---|---|
| `ENVIRONMENT` | yes | no | Must be `production`. Turns on strict startup checks and turns API docs off. |
| `DEBUG` | yes | no | Must be false; the app refuses to start otherwise (it would log all SQL). |
| `PROJECT_NAME` | yes | no | Display name of the API. No default: startup fails if missing. |
| `VERSION` | yes | no | API version string. No default. |
| `DATABASE_URL` | yes | **yes** | Neon PostgreSQL connection string, `postgresql://` scheme, ending in `?sslmode=require`. Use a database separate from development. Also used by Alembic, which ignores the `DB_*` settings below. |
| `SECRET_KEY` | yes | **yes** | Random token-signing key. No default; validated: at least 32 non-whitespace characters and not a placeholder. Unique to production, never reused. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | yes | no | Login token lifetime in minutes (1 to 1440). |
| `CORS_ORIGINS` | yes | no | Comma-separated https origin(s) of the frontend, no trailing path, no wildcard. Must include the exact Pages address visitors use. |
| `AI_PROVIDER` | yes | no | Must be `groq` in production. Any other value (the paid `openai` provider included) makes startup fail, even while AI is off, and `get_ai_client()` refuses it again at call time. There is no fallback to another provider. Local development still accepts `openai`. |
| `MODEL_NAME` | yes | no | Model identifier available to your Groq account. |
| `GROQ_API_KEY` | only while `AI_ENABLED` is true | **yes** | Groq API key (free tier). Not needed (and not checked) while AI is off. Never add a payment method to the Groq account: that moves it to the paid Developer tier. |
| `AI_ENABLED` | no (default true in development, **false in production when absent**; `render.yaml` also sets false) | no | Master switch for model-backed chat. False makes `/ai/chat` and `/ai/chat/stream` return 503 at once. The initial deployment keeps it false; enable it through a reviewed change (`docs/DEPLOYMENT.md`, "Enabling AI later"). |
| `REGISTRATION_ENABLED` | no (default true in development, **false in production when absent**; `render.yaml` also sets false) | no | Keep false for the demo so nobody can sign up. The demo account is created by `scripts/seed_demo_user.py`. |
| `PYTHON_VERSION` | recommended | no | Render's Python runtime version (set in `render.yaml`). |
| `PORT` | injected by Render | no | Used by the start command. Do not set it yourself. |
| `ALGORITHM` | no | no | Only `HS256` is accepted. |
| `ENABLE_DOCS` | no | no | Controls `/docs`, `/redoc` and `/openapi.json`. Unset already means off in production; `render.yaml` sets it to false explicitly. |
| `OPENAI_API_KEY` | no | **yes** | Leave unset. Production refuses `AI_PROVIDER=openai`, so the key would never be used. |
| `HOST` | no | no | Read by the settings but unused by the start command. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | no | no | Pool sizing per process (defaults 5 and 5). Keep the total under the database's connection limit. |
| `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT`, `DB_CONNECT_TIMEOUT` | no | no | Seconds. Defaults suit a database that sleeps when idle. |
| `DB_SSLMODE` | no | no | Unset means `require` in production. A `sslmode` written in `DATABASE_URL` wins. |

### Rate limits, AI quotas and stream limits (enforced)

| Variable | Default | Where it is kept | What it does |
|---|---|---|---|
| `RATE_LIMIT_AUTH_PER_MINUTE` | 10 | process memory | Attempts per minute per client address on `POST /auth/login`, counted separately on `POST /auth/register`. Over the limit: HTTP 429 with a `Retry-After` header, before any account lookup. |
| `RATE_LIMIT_AI_PER_MINUTE` | 10 | process memory | Requests per minute per signed-in user, shared by `/ai/chat` and `/ai/chat/stream`. |
| `AI_DAILY_REQUESTS_PER_USER` | 10 | database (`ai_usage_daily`) | Model requests per user per UTC day (chat and stream share it). |
| `AI_DAILY_REQUESTS_GLOBAL` | 80 | database | Model requests per UTC day across all users. |
| `AI_DAILY_TOKENS_GLOBAL` | 150000 | database | Tokens per UTC day across all users. There is no per-user token setting. |
| `AI_MAX_CONCURRENT_STREAMS` | 3 | process memory | Simultaneous `/ai/chat/stream` responses. Excess streams get HTTP 429 with `Retry-After: 5`. |
| `TRUSTED_PROXY_COUNT` | 0 | n/a | How many reverse proxies in front of the app write `X-Forwarded-For`. See below. |

Exceeding a daily quota returns HTTP 429 with `Retry-After` set to the seconds left until 00:00 UTC. Counters reset at 00:00 UTC.

**Token measurement and quota semantics.** A request reserves a conservative allowance up front (about 4,000 input tokens plus the output cap), then the reservation is replaced by the measured value: the provider's `total_tokens` when it reports one (actual usage), otherwise `ceil(characters / 4)` over the prompt and the generated text (an estimate; code and non-English text tokenize differently). For non-streaming requests that use tool rounds, only the first prompt is counted when the provider reports nothing, so such requests can be under-counted. A request that fails without output is refunded (request and tokens); one that fails after partial output counts what was produced.
- The request limits (`AI_DAILY_REQUESTS_PER_USER`, `AI_DAILY_REQUESTS_GLOBAL`) are exact.
- `AI_DAILY_TOKENS_GLOBAL` is checked atomically against reservations but is **not a strict hard cap**: the measured value can exceed the reservation, so the real total can pass the limit by the overshoot of the requests in flight. An overshoot is logged as a warning.
- There is **no per-user token quota**; a user is limited only by their request count.
- If the database definitely rejects a settlement or refund, the reservation stays counted (over-counted, not lost), it is retried once more at the end of the request, and the failure is logged with the error class only.
- **Not exactly-once.** A commit exception can be ambiguous: the server may have committed and only the acknowledgement was lost. The code cannot tell, treats it as failed, and the retry may apply the adjustment twice (a settle can under-count by up to reserved-minus-actual tokens, a release can refund the request and tokens twice). This is accepted for a single-instance demo; closing it would need a durable idempotency record per reservation, which is not implemented. A test pins this limitation.

**`TRUSTED_PROXY_COUNT` (UNRESOLVED for Render).** The default 0 ignores `X-Forwarded-For` (any client can send it) and limits by the socket address. Behind Render's proxy that address is the proxy's, so all visitors share one login bucket. With N > 0 the app takes the Nth entry from the right of `X-Forwarded-For` (repeated header lines are joined first) and ignores everything to its left; a missing, short or non-IP entry falls back to the socket address, so forged or malformed headers cannot select another bucket. Evidence on Render so far: its documentation says traffic passes through Cloudflare and its load balancers and the real client address is in `X-Forwarded-For`, but it does not state how many entries are appended or that client-supplied entries are removed; one third-party capture shows the client address followed by two proxy addresses, which is not authoritative. A value larger than the true hop count would select a client-controlled entry, so **the value stays 0 and public login exposure remains blocked until it is verified**. To verify: deploy with AI off, call a temporary diagnostic from several networks while sending a forged `X-Forwarded-For`, compare the received header with your real address, and set the count only if the position is stable and the forged entry sits to its left. Keys and logs hold only a hash of the address, never the address.

**Limits of this enforcement.** Stream slots use an idle lease renewed by every chunk plus a 10-minute maximum per stream (see `docs/DEPLOYMENT.md`); a stream silent for 5 minutes loses its slot, so the stream cap is not a hard guarantee in that case. The per-minute limits and stream slots live in the memory of one process: correct for the single Render instance and single uvicorn worker used here, reset on every restart or deploy, and not shared between instances or workers. Only the daily quotas survive restarts and are enforced in the database; they are atomic across concurrent requests. Nothing here is distributed enforcement.

## Health endpoints (no variables, listed for clarity)

| Path | Kind | Touches the database | Use |
|---|---|---|---|
| `/health/` | liveness | no | Render `healthCheckPath`. Returns 200 whenever the process is up. |
| `/health/ready` | readiness | yes (`SELECT 1`) | Manual smoke tests only. 200 when the database answers, 503 otherwise. Not a Render health check: polling it would keep the Neon free-plan compute awake. |

## One-off seed command only (never store these on the service)

| Variable | Description |
|---|---|
| `DEMO_USER_USERNAME` | Username of the demo account. |
| `DEMO_USER_EMAIL` | Email of the demo account (also accepted at login). |
| `DEMO_USER_PASSWORD` | Password, 12 to 72 bytes. Type it only on the command line of the seed command. |

## Frontend (Cloudflare Pages)

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | yes | Origin of the Render API (https, no path). Read at build time; the production build fails if it is missing, not https, or points at localhost. Changing it needs a new build. |
| `NODE_VERSION` | optional | Only if `frontend/.node-version` is not picked up by the build. |
