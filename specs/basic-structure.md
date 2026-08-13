# Basic Structure (Phase 1 — Infrastructure) — Implementation Plan

## Summary

Stand up the monorepo skeleton for the PDF RAG Chat app described in `PRD.md`: a Turborepo containing a FastAPI backend (with a Celery worker sharing the same Python package), a React + Vite frontend, and docker-compose infra (Postgres 16 + pgvector, Redis 7). No product features — this phase delivers the scaffolding, configuration, migration machinery, and quality tooling that Phases 2–6 build on.

Doing it now (before ingestion code) locks in the decisions that are expensive to retrofit: async-vs-sync DB sessions, the worker process boundary, and where migrations live.

## Success Criteria

- `docker compose up -d` brings up postgres, redis, api, worker; all four report healthy.
- `curl localhost:8000/health` returns `{"status":"ok","database":"ok","redis":"ok"}` in under 200 ms.
- `uv run alembic upgrade head` on an empty database succeeds and `SELECT extversion FROM pg_extension WHERE extname='vector'` returns a row.
- `pnpm dev` starts Vite on `localhost:5173`; the page fetches `/api/health` through the Vite proxy and renders the status — proving the frontend↔backend wiring end-to-end.
- `pnpm lint`, `pnpm typecheck`, `pnpm test` all pass from the repo root, covering both apps via Turborepo.
- A Celery task (`ping`) dispatched from a pytest test is executed by the worker and returns `"pong"`.

## Scope & Constraints

**In scope**
- pnpm workspace + Turborepo pipeline covering a Python app and a TS app
- FastAPI app: settings, lifespan, CORS, router registration, `/health`
- SQLAlchemy 2.0 dual session layer (async for API, sync for worker) + declarative base
- Alembic configured; one migration: `CREATE EXTENSION vector`
- Celery app + Redis broker/backend, one `ping` task, worker container
- React 19 + TS + Vite + Tailwind + shadcn/ui init + React Router + TanStack Query, one route that calls `/health`
- docker-compose: postgres (pgvector image), redis, api, worker — web runs on host
- ruff, mypy, pytest, vitest, eslint, prettier — all wired into turbo tasks
- `.env.example`, config loading, README quickstart

**Out of scope (deferred to Phase 2+)**
- All domain tables (`documents`, `sections`, `chunks`, `conversations`, `messages`, `message_sources`) and the HNSW index — Phase 2 owns them
- Any ingestion, retrieval, chat, or LLM/OpenAI client code
- Shared TS type package / OpenAPI codegen — **explicitly rejected**, each app owns its types
- Auth, CI pipeline, production Dockerfiles, deployment

**Hard constraints**
- Single-user local app — no auth, no multi-tenancy anywhere in the structure
- Python 3.12, Node 22, pnpm 9, Turborepo 2.x
- Frontend runs natively on host (fast HMR); backend + infra in Docker
- A local `uv` venv must also exist so PyCharm resolves imports and `pnpm lint/test` run without Docker

**Trade-offs**
- Two DB engines (asyncpg + psycopg) instead of one, to keep both FastAPI and Celery idiomatic. Cost: two session factories to configure. Benefit: no `asyncio.run()` inside prefork workers.
- API in Docker but tests/lint on host means the `DATABASE_URL` differs by context (`postgres:5432` vs `localhost:5432`). Handled with an env override in compose, documented in `.env.example`.
- Celery (heavier than arq) chosen by the user; accepted. Structure isolates it behind `worker/tasks.py` so the broker could be swapped later.

## Architecture & Design

### High-Level Flow

```
host                                  docker network
─────────────────────────────         ────────────────────────────────────
pnpm dev (turbo)
  └─ apps/web  vite :5173
        │ /api/* proxied
        ▼
     ──────────────────────────────►  api (uvicorn :8000)
                                        │ async SQLAlchemy (asyncpg)
                                        ├──────────────► postgres:5432 (pgvector)
                                        │ celery.send_task
                                        └──────────────► redis:6379
                                                            ▲
                                      worker (celery)  ─────┘
                                        │ sync SQLAlchemy (psycopg)
                                        └──────────────► postgres:5432

uv run pytest / ruff / mypy  ────────► localhost:5432, localhost:6379 (published ports)
```

### Repository Layout

```
ai-book-chat/
├── package.json                 # root: pnpm workspaces, turbo scripts
├── pnpm-workspace.yaml
├── turbo.json
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── PRD.md
├── specs/
└── apps/
    ├── api/
    │   ├── package.json         # turbo shim → uv run …
    │   ├── pyproject.toml       # deps + ruff/mypy/pytest config
    │   ├── uv.lock
    │   ├── Dockerfile           # single image, two commands (api / worker)
    │   ├── alembic.ini
    │   ├── alembic/
    │   │   ├── env.py
    │   │   └── versions/
    │   │       └── 0001_enable_pgvector.py
    │   ├── src/app/
    │   │   ├── __init__.py
    │   │   ├── main.py          # FastAPI factory, lifespan, CORS, routers
    │   │   ├── config.py        # pydantic-settings Settings
    │   │   ├── logging.py       # structured logging setup
    │   │   ├── api/
    │   │   │   ├── deps.py      # get_db async session dependency
    │   │   │   └── routes/
    │   │   │       ├── __init__.py
    │   │   │       └── health.py
    │   │   ├── db/
    │   │   │   ├── base.py      # DeclarativeBase + naming convention
    │   │   │   ├── session.py   # async engine/sessionmaker (API)
    │   │   │   ├── sync_session.py  # sync engine/sessionmaker (worker)
    │   │   │   └── models/__init__.py   # empty in Phase 1
    │   │   └── worker/
    │   │       ├── celery_app.py
    │   │       └── tasks.py     # ping task only
    │   └── tests/
    │       ├── conftest.py
    │       ├── test_health.py
    │       └── test_worker.py
    └── web/
        ├── package.json
        ├── vite.config.ts       # /api proxy → localhost:8000
        ├── tsconfig.json
        ├── tailwind.config.ts
        ├── components.json      # shadcn/ui
        ├── index.html
        └── src/
            ├── main.tsx         # QueryClientProvider + RouterProvider
            ├── router.tsx
            ├── api/client.ts    # fetch wrapper, base = /api
            ├── types/index.ts   # app-local types (NOT shared)
            ├── components/ui/   # shadcn output
            ├── layouts/AppLayout.tsx   # sidebar + main panel shell
            └── routes/HealthPage.tsx
```

Rationale for `apps/api` holding both the web server and the worker: they share models, config, and DB session code. Splitting them into two packages would force a third shared Python package for zero benefit in a single-user app. The process boundary is enforced by the compose service command, not by the package layout.

### Key Configuration

**`turbo.json`** — tasks: `dev` (persistent, no cache), `build`, `lint`, `typecheck`, `test`, `format`. Python tasks are not cacheable by content hash out of the box, so `apps/api` declares `inputs: ["src/**", "tests/**", "pyproject.toml"]` for `lint`/`test` to get correct caching.

**`apps/api/package.json`** — a shim so Turborepo can orchestrate Python:
```json
{
  "name": "@ai-book-chat/api",
  "scripts": {
    "dev": "docker compose up api worker",
    "lint": "uv run ruff check . && uv run ruff format --check .",
    "format": "uv run ruff format .",
    "typecheck": "uv run mypy src",
    "test": "uv run pytest",
    "migrate": "uv run alembic upgrade head"
  }
}
```

**`config.py`** — `pydantic-settings` `Settings` with: `database_url`, `sync_database_url` (derived from `database_url` by swapping the driver), `redis_url`, `celery_broker_url`, `celery_result_backend`, `upload_dir`, `max_upload_mb=50`, `cors_origins`, `log_level`. Placeholders `openai_api_key` / `anthropic_api_key` declared as `str | None` now so Phase 2 doesn't touch config plumbing.

**`db/session.py` (async, API)**
```python
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```
**`db/sync_session.py` (sync, worker)**
```python
sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
```
Both import models from the same `db/base.py` `Base`, so Alembic autogenerate sees one metadata.

**Alembic** — `env.py` uses the **sync** engine (simplest, standard) and imports `app.db.base.Base` plus `app.db.models` for `target_metadata`. Migration `0001`:
```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
def downgrade():
    op.execute("DROP EXTENSION IF EXISTS vector")
```

**`docker-compose.yml`**
| service | image / build | notes |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | named volume, port 5432 published, healthcheck `pg_isready` |
| `redis` | `redis:7-alpine` | port 6379 published, healthcheck `redis-cli ping` |
| `api` | build `apps/api` | `uvicorn app.main:app --reload`, `src/` bind-mounted, uploads volume, depends_on healthy postgres+redis |
| `worker` | same build | `celery -A app.worker.celery_app worker -l info`, same mounts |

`api`/`worker` get `DATABASE_URL=postgresql+asyncpg://…@postgres:5432/…` via compose `environment`, overriding the host-facing `localhost` value in `.env`.

**`vite.config.ts`** — `server.proxy['/api'] = { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '') }`. Frontend always calls `/api/...`; no CORS in dev. FastAPI still gets `CORSMiddleware` with `settings.cors_origins` for the case where the frontend is pointed straight at :8000.

### Alternative Approaches Considered

**Monorepo tool**
- *Turborepo* (chosen, user-specified): good task graph + caching, trivially wraps non-JS apps via package.json shims.
- *Nx*: stronger Python plugin story, but heavier and more opinionated.
- *Plain pnpm workspaces + Makefile*: less machinery, but no task graph or caching.

**Python in the task graph**
- *uv + package.json shim* (chosen): one lockfile, ~10x faster installs than Poetry, `uv run` needs no venv activation, and Turborepo stays the single entry point.
- *Poetry*: mature, slower, and adds a venv-activation step in Docker.
- *Python outside turbo*: simpler, but `pnpm lint` at root would silently skip the backend.

**API/worker packaging**
- *One package, two commands* (chosen): shared models/config with no third package.
- *Separate `apps/worker` package*: cleaner process boundary, but forces `packages/core` for shared models — premature for this size.

**DB sessions** — dual engine chosen (user decision); see Trade-offs. `asyncio.run()` inside Celery prefork was rejected due to known event-loop/connection-pool reuse bugs.

**Frontend data layer** — TanStack Query chosen (user decision); it directly serves the PRD's status polling requirement (US-1) with `refetchInterval` while `status !== READY`, which hand-rolled `useEffect` polling handles badly.

## Implementation Steps

1. **Repo init** — `git init`, `.gitignore` (node_modules, `.venv`, `__pycache__`, `.env`, `uploads/`, `.turbo`, `dist`), root `package.json` (`packageManager: pnpm@9`), `pnpm-workspace.yaml` (`apps/*`), install `turbo` as a root devDependency.
2. **`turbo.json`** — define `dev`/`build`/`lint`/`typecheck`/`test`/`format` tasks with dependencies and cache inputs; root scripts delegate to `turbo run <task>`.
3. **Infra compose (part 1)** — `docker-compose.yml` with `postgres` + `redis` only, healthchecks, named volumes, published ports. Verify: `docker compose up -d && docker compose ps` shows both healthy.
4. **Python project** — `apps/api/pyproject.toml` with deps (`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `psycopg[binary]`, `alembic`, `pydantic-settings`, `celery[redis]`, `redis`, `pgvector`, `python-multipart`) and dev deps (`pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`). `uv sync` creates `.venv` + `uv.lock`.
5. **Config + logging** — `app/config.py` (`Settings`, cached `get_settings()`), `app/logging.py`. Write `.env.example` with host-facing URLs.
6. **DB layer** — `db/base.py` (`Base` with index/constraint naming convention), `db/session.py`, `db/sync_session.py`, empty `db/models/__init__.py`, `api/deps.py` `get_db()` yielding an `AsyncSession`.
7. **Alembic** — `alembic init`, rewire `env.py` to `Settings.sync_database_url` and `Base.metadata`, set `file_template` for ordered revision filenames, write migration `0001_enable_pgvector`. Verify: `uv run alembic upgrade head` then `downgrade base` then `upgrade head` again, all clean.
8. **FastAPI app** — `main.py` with an app factory, lifespan (dispose engines on shutdown), `CORSMiddleware`, router include under no prefix. `routes/health.py`: `SELECT 1` through the async session + `redis.ping()`, returning per-dependency status and HTTP 503 if either fails.
9. **Celery** — `worker/celery_app.py` (broker/backend from settings, `task_serializer="json"`, `timezone="UTC"`), `worker/tasks.py` with `@shared_task ping() -> "pong"`. Confirm the app auto-discovers `app.worker.tasks`.
10. **API Dockerfile + compose (part 2)** — `python:3.12-slim` base, copy `uv` binary, `uv sync --frozen`, non-root user, `src/` bind mount for reload. Add `api` and `worker` services. Verify: `curl localhost:8000/health` → ok; `docker compose logs worker` shows the ping task registered.
11. **Backend tests** — `conftest.py` (event-loop policy, `httpx.ASGITransport` client fixture, DB URL pointing at localhost), `test_health.py` (200 + all-ok payload), `test_worker.py` (dispatch `ping` with a real broker, assert `"pong"`; skip if Redis is unreachable). `uv run pytest` green.
12. **Web app scaffold** — `pnpm create vite apps/web --template react-ts`, then Tailwind v4 + `shadcn init` + install `react-router` and `@tanstack/react-query`. Configure `vite.config.ts` proxy and the `@/` path alias in tsconfig + vite.
13. **Web shell** — `main.tsx` (QueryClientProvider + RouterProvider), `router.tsx` (routes `/` → HealthPage, `/documents` placeholder), `layouts/AppLayout.tsx` (sidebar + main panel per PRD §7), `api/client.ts` (typed `request<T>()` over fetch, base `/api`, error normalization), `routes/HealthPage.tsx` using `useQuery` against `/health` and rendering status with shadcn `Badge`/`Card`.
14. **Web tooling** — eslint (flat config) + prettier + vitest with one render smoke test for `HealthPage` (mocked fetch). `pnpm --filter web test` green.
15. **Root wiring + docs** — verify `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm dev` from the root traverse both apps. Write `README.md`: prerequisites, `cp .env.example .env`, `pnpm install && uv sync`, `docker compose up -d`, `pnpm --filter api migrate`, `pnpm dev`, and a troubleshooting note on the two `DATABASE_URL` values.

### Risks & Mitigations

- **Turbo can't hash Python deps, so `test`/`lint` cache goes stale or over-fires.**
  - Declare explicit `inputs` (`src/**`, `tests/**`, `pyproject.toml`, `uv.lock`) on those tasks.
  - If it still misbehaves, mark the api tasks `"cache": false` — correctness over speed at this size.
- **`DATABASE_URL` mismatch between host tooling and containers** (tests hit `postgres:5432` and hang, or the container hits `localhost`).
  - `.env` holds the host-facing URL; compose `environment:` overrides for `api`/`worker` only. Documented in README and `.env.example` comments.
  - `/health` reports which host it actually connected to at `debug` log level.
- **Dual engines drift** — someone adds a model that only one metadata sees, and Alembic autogenerate drops tables.
  - Single `Base` in `db/base.py`; `db/models/__init__.py` re-exports every model and `alembic/env.py` imports that module. Add a test in Phase 2 asserting `Base.metadata.tables` is non-empty and matches the migration head.
- **Celery prefork + SQLAlchemy connection sharing across forks** → `InterfaceError` under load.
  - Worker uses its own sync engine created lazily per process; add `worker_process_init` signal calling `sync_engine.dispose()`.
- **shadcn/ui + Tailwind v4 + React 19 setup churn** — the init flow changes often and can produce a broken config.
  - Run `shadcn init` early (step 12) and immediately add one component (`button`) as a smoke test before building the layout. If it fights the toolchain, fall back to Tailwind-only and add shadcn components by hand in Phase 5.
- **pgvector extension requires superuser** on non-Docker Postgres.
  - The `pgvector/pgvector:pg16` image runs migrations as the superuser owner, so this is fine locally; README notes the requirement for any other environment.

## Test Strategy

**Unit / integration (pytest, `apps/api/tests`)**
- `test_health.py::test_health_ok` — 200, payload `{status, database, redis}` all `"ok"`.
- `test_health.py::test_health_db_down` — DB dependency overridden to raise → 503, `database: "error"`.
- `test_worker.py::test_ping_task` — `ping.delay()` against the real Redis broker returns `"pong"` within 10 s; `pytest.skip` if Redis is down.
- `test_config.py::test_sync_url_derivation` — `postgresql+asyncpg://…` → `postgresql+psycopg://…`.
- Alembic round-trip: `test_migrations.py` runs `upgrade head` → `downgrade base` → `upgrade head` on a scratch database.

**Unit (vitest, `apps/web`)**
- `HealthPage` renders a loading state, then the ok badge, with fetch mocked.
- `api/client` throws a normalized error on a non-2xx response.

**Manual verification**
1. `docker compose down -v` then full quickstart from README → healthy stack from a clean slate.
2. Kill the `postgres` container → `/health` returns 503 with `database: "error"`, and the Vite page shows the degraded state instead of crashing.
3. Edit `health.py` → uvicorn reloads inside the container (bind mount works).
4. Edit `HealthPage.tsx` → HMR updates without a full reload.
5. `pnpm build` produces `apps/web/dist`.

**Performance** — not meaningful in Phase 1 beyond `/health` p50 under 200 ms locally; the PRD's targets (2 min ingest, 3 s first token) are Phase 2–4 concerns.

## Success Checklist

- [ ] All six success criteria verified with pasted command output
- [ ] `pnpm lint && pnpm typecheck && pnpm test` green at the root
- [ ] Clean-slate run (`docker compose down -v` → README steps) works verbatim
- [ ] `.env.example` complete; no secrets committed; `.env` in `.gitignore`
- [ ] README quickstart + the dual-`DATABASE_URL` gotcha documented
- [ ] Alembic upgrade/downgrade round-trips cleanly
- [ ] No domain tables or feature code leaked into this phase

## Timeline & Estimates

| Phase | Work | Estimate |
|---|---|---|
| Steps 1–3 | Monorepo + turbo + infra compose | ~1.5 h |
| Steps 4–9 | Python project, config, DB, Alembic, FastAPI, Celery | ~3 h |
| Steps 10–11 | Dockerfile, api/worker services, backend tests | ~2 h |
| Steps 12–14 | Web scaffold, shell, tooling, tests | ~2.5 h |
| Step 15 | Root wiring, docs, clean-slate verification | ~1 h |
| **Total** | | **~10 h** (+2 h buffer for shadcn/Tailwind v4 churn) |

## Open Questions

None blocking. Defaults chosen where the answer doesn't change the structure:
- Python 3.12, Node 22, pnpm 9, Turborepo 2.x, React 19, Vite 6, Tailwind v4
- Uploaded PDFs land in a Docker named volume mounted at `/data/uploads`, `UPLOAD_DIR` configurable
- Structured JSON logging via stdlib `logging` — no structlog dependency yet

Flag now if any default is wrong; each is cheap to change in Phase 1 and expensive later.