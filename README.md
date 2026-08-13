# PDF RAG Chat

Upload a book (PDF), ask questions in natural language, get grounded answers with page citations.
See [PRD.md](./PRD.md) for the product spec and [specs/](./specs) for implementation plans.

**Current state: Phase 1 (infrastructure) only.** No ingestion, retrieval or chat yet.

## Stack

| Layer | Choice |
| --- | --- |
| Monorepo | pnpm workspaces + Turborepo |
| Backend | FastAPI (Python 3.12, uv) — `apps/api` |
| Worker | Celery + Redis — same package, separate process |
| Database | PostgreSQL 16 + pgvector |
| Frontend | React 19 + Vite + Tailwind v4 + shadcn/ui + TanStack Query + React Router — `apps/web` |

## Prerequisites

Node 22+, pnpm 11+, uv 0.10+, Docker with Compose v2.

## Quickstart

```bash
cp .env.example .env
pnpm install                      # workspace JS deps
(cd apps/api && uv sync)          # backend venv (also what PyCharm should point at)

docker compose up -d --build      # postgres, redis, api, worker
pnpm --filter @ai-book-chat/api migrate   # alembic upgrade head

pnpm dev                          # vite on :5173 (+ attaches to api/worker logs)
```

Then open http://localhost:5173 — the Status page renders live `/health` from FastAPI.

Check the backend directly:

```bash
curl localhost:8000/health
# {"status":"ok","database":"ok","redis":"ok"}
```

## Commands

Run from the repo root; Turborepo fans them out to both apps.

| Command | Does |
| --- | --- |
| `pnpm dev` | Vite dev server + `docker compose up api worker` |
| `pnpm lint` | ruff (api) + eslint (web) |
| `pnpm typecheck` | mypy (api) + tsc (web) |
| `pnpm test` | pytest (api) + vitest (web) |
| `pnpm build` | Vite production build |
| `pnpm format` | ruff format + prettier |
| `pnpm infra:up` / `pnpm infra:down` | Just postgres + redis |

Backend-only helpers: `pnpm --filter @ai-book-chat/api migrate`, `... makemigration "message"`.

## Gotchas

**Two `DATABASE_URL` values.** `.env` holds the host-facing URLs (`localhost:5432`, `localhost:6379`)
used by `uv run pytest`, `uv run alembic` and your IDE. `docker-compose.yml` overrides
`DATABASE_URL`/`REDIS_URL`/`CELERY_*` for the `api` and `worker` services to the in-network
hostnames (`postgres`, `redis`). Environment variables beat the dotenv file, so nothing to
toggle by hand — but a "connection refused to postgres:5432" from a host command means the
container env leaked into your shell.

**Backend tests need the infra up.** `pytest` talks to the real Postgres and Redis on localhost.
The Celery round-trip test skips itself if no worker is consuming the queue.

**Migrations.** Alembic runs through the sync (psycopg) driver even though the API uses asyncpg.
Revision ids are explicit and ordered (`0001`, `0002`, …); pass `--rev-id` when autogenerating.
Phase 1 ships one migration: `CREATE EXTENSION vector`. Domain tables land in Phase 2.

**Uploads.** Default `<repo>/uploads` on the host; the containers use the `uploads_data` volume
mounted at `/data/uploads`.

## Layout

```
apps/api/src/app/     FastAPI app, config, db (async + sync sessions), Celery worker
apps/api/alembic/     migrations
apps/web/src/         routes, layouts, api client, shadcn components (types are app-local)
docker-compose.yml    postgres, redis, api, worker
specs/                implementation plans
```
