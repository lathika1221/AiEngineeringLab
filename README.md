# AIEngineeringLab (LATZ)

LATZ is a multi-user AI engineering workspace for working with LLM-powered workflows, projects, goals, memories and streamed conversations. The application combines a React frontend with a FastAPI backend and PostgreSQL persistence.

**Live application:** https://latz-ai.pages.dev  
**Repository:** https://github.com/lathika1221/AiEngineeringLab

## What it does

- Provides authenticated, user-scoped workspaces for conversations, projects, goals and memories.
- Streams LLM responses and reports whether a response completed, reached its output limit or ended unexpectedly.
- Supports five engineering modes: Forge, Learn, Research, Explore and Solve.
- Supports constrained function calling through a calculator tool with syntax-tree allow-listing.
- Maintains user-confirmed, rule-based contextual memories and assembles relevant context for conversations.
- Includes profile and settings pages, project details, conversation management and an experiments workspace.

## Architecture

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite, React Router |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Database and migrations | PostgreSQL, Alembic |
| LLM integration | Groq API, OpenAI-compatible SDK, `openai/gpt-oss-20b` |
| Testing and CI | pytest, frontend tests, GitHub Actions |
| Deployment | Cloudflare Pages (frontend), Railway (API), Neon PostgreSQL |

## Engineering highlights

- **Multi-user data isolation:** user-owned resources are scoped to the authenticated account and covered by cross-account tests.
- **Streaming reliability:** stream-end markers distinguish successful completion from length limits, provider errors and incomplete streams; partial output is retained with an explanatory note where applicable.
- **Contextual memory:** memory candidates are detected by rules, confirmed by the user and ranked for context assembly. This is not an embeddings-based or vector-database memory system.
- **Constrained tool execution:** function calling is limited to a calculator whose accepted syntax-tree nodes are explicitly allow-listed; arbitrary `eval` execution is not used.
- **Abuse and capacity controls:** database-backed daily request quotas work alongside per-user rate limits and leased concurrent-stream slots.
- **Account security:** bcrypt password hashing, JWT authentication, token invalidation after password changes and account-scoped data access.
- **Automated checks:** backend and frontend test suites, linting, builds and dependency auditing are included in CI.

## Run locally

### Backend

Create and activate a Python virtual environment, then install dependencies:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and provide local development values. Do not commit real secrets.

Run database migrations and start the API:

```bash
alembic upgrade head
uvicorn src.api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend uses `http://127.0.0.1:8000` by default for local backend access. Set `VITE_API_URL` in `frontend/.env.local` to use another API origin.

## Tests and quality checks

Backend:

```bash
pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm test
npm run build
```

See the GitHub Actions workflow in `.github/workflows/ci.yml` for the CI checks.

## Documentation

- [Backend changes](docs/BACKEND_CHANGES.md)
- [Operations, capacity and security posture](docs/OPERATIONS.md)
- [Environment variable reference](docs/ENVIRONMENT.md)
- [Frontend architecture and routes](frontend/docs/LATZ_FRONTEND.md)
- [Frontend/backend gaps](frontend/docs/BACKEND_GAPS.md)

**Deployment note:** the live stack currently uses Railway for the API, Cloudflare Pages for the frontend and Neon PostgreSQL. The existing deployment runbook contains older Render-oriented instructions and should not be treated as the current Railway deployment procedure.

## Current scope and limitations

LATZ is a controlled-beta portfolio project, not a claim of large-scale production operation. The current deployment uses a single backend replica; in-memory rate limits and stream slots are not distributed across multiple replicas. The Content Security Policy is report-only, and public registration is closed. Review [operations documentation](docs/OPERATIONS.md) before changing deployment settings or increasing quotas.

## License

No open-source license has been added yet. All rights remain with the repository owner unless a license is added.
