# GitHub Actions CI/CD Plan

## Summary
Automate linting, type-checking, testing, building, and deploying for a Python/TypeScript monorepo (FastAPI backend + React frontend). Two workflows: `ci.yml` validates and builds, `deploy.yml` ships a release tag to staging or production.

## Success Criteria
- All PRs run lint, type-check, and tests before review
- Checks pass before merge to main (required status checks)
- Every merge to main lints, tests, and builds the Docker image and frontend bundle
- Deploys are manual, from a release tag, to staging or production
- A deploy never runs unless CI passes on the tagged commit first
- CI run time <10 minutes per run

## Scope & Constraints
- **In scope:** PR checks, build on merge to main, tag-based deploy to staging/production, Docker image publishing to GHCR
- **Out of scope:** Cross-browser testing, load testing, security scanning (can add later)
- **Hard constraints:** Must work with existing Turbo, uv, pnpm setup; no changes to local dev workflow
- **Versions:** Python 3.12, Node 22, pnpm from `packageManager` in root `package.json`

## Architecture & Design

### High-Level Flow
```
PR opened/updated            (ci.yml)
  └─→ changes (paths filter: api / web)
        ├─→ lint-backend, test-backend    if apps/api changed
        └─→ lint-frontend, test-frontend  if apps/web / pnpm-lock changed

Push to main                 (ci.yml)
  ├─→ lint-backend, test-backend, lint-frontend, test-frontend
  ├─→ build-backend   (after backend lint + test) → ghcr.io/<repo>/api:main, :main-<sha7>
  └─→ build-frontend  (after frontend lint + test) → `frontend-build` artifact

Manual run from a tag        (deploy.yml, workflow_dispatch)
  ├─→ check-ref   fail unless the selected ref is a tag
  ├─→ ci          calls ci.yml on the tag: lint, test, build, push api:<tag>
  └─→ deploy      environment = staging | production (dropdown)
```

### Key Changes

#### 1. Workflow Files (`.github/workflows/`)

| File | Purpose | Trigger |
|------|---------|---------|
| `ci.yml` | Lint, test, and build both apps | PR, push to main, `workflow_call`, manual |
| `deploy.yml` | Run CI on a tag, then deploy to staging or production | Manual (`workflow_dispatch`) from a tag only |

**`ci.yml` jobs**

| Job | What it does | When it runs |
|-----|--------------|--------------|
| `changes` | `dorny/paths-filter` → `api` / `web` outputs | PRs only |
| `lint-backend` | Ruff, MyPy, import-linter | PR if `apps/api` changed; always otherwise |
| `test-backend` | pytest against a `pgvector/pgvector:pg16` service container | PR if `apps/api` changed; always otherwise |
| `lint-frontend` | ESLint, TypeScript check | PR if `apps/web` / `pnpm-lock.yaml` changed; always otherwise |
| `test-frontend` | Vitest | PR if `apps/web` / `pnpm-lock.yaml` changed; always otherwise |
| `build-backend` | Docker build + push to GHCR, upload `image-metadata` artifact | Not on PRs; needs backend lint + test to pass |
| `build-frontend` | `pnpm run build`, upload `frontend-build` artifact | Not on PRs; needs frontend lint + test to pass |

Concurrency group is `${{ github.workflow }}-${{ github.ref }}`. Only superseded PR runs are cancelled, never runs on main or runs called from deploy.

**`deploy.yml` jobs**

| Job | What it does |
|-----|--------------|
| `check-ref` | Errors unless `github.ref_type == 'tag'` |
| `ci` | Reusable call of `ci.yml` for the tagged commit |
| `deploy` | Downloads `frontend-build`, deploys image `ghcr.io/<repo>/api:<tag>` to the chosen environment, health check, notify |

Only one deploy runs at a time (`concurrency: deploy`, no cancel).

#### 2. Image Tags

| Ref | Tags pushed |
|-----|-------------|
| `main` branch | `main`, `main-<sha7>`, `latest-<sha7>` |
| `v*` tag (via deploy) | `<tag>` (e.g. `v1.2.3`) |

Deploy always uses the tag name as the image tag. The image is rebuilt from the tagged commit during the deploy run.

#### 3. Environment & Secrets Configuration

- **Registry:** GHCR. Login uses the built-in `GITHUB_TOKEN` (`packages: write` on the build job). No Docker Hub secrets needed.
- **Permissions:** workflows default to `contents: read`. The `ci` job in `deploy.yml` grants `packages: write` and `pull-requests: read` because a called workflow cannot exceed its caller's permissions.
- **GitHub Environments:** create `staging` and `production` in Settings → Environments. Add required reviewers to `production`.
- **Environment secrets** (set per environment once real deploy commands replace the current TODO stubs):
  - `DEPLOY_KEY` — SSH key or API token for the target
  - `DATABASE_URL`, `REDIS_URL` — connection strings
  - `LLM_API_KEY` — if environment-specific

**Actions used**

| Action | Version |
|--------|---------|
| `actions/checkout` | v7 |
| `actions/setup-python` | v7 |
| `actions/setup-node` | v7 |
| `actions/upload-artifact` | v7 |
| `actions/download-artifact` | v8 |
| `astral-sh/setup-uv` | v10 |
| `pnpm/action-setup` | v6 |
| `dorny/paths-filter` | v4 |
| `docker/setup-buildx-action` | v4 |
| `docker/login-action` | v4 |
| `docker/metadata-action` | v6 |
| `docker/build-push-action` | v7 |

#### 4. Dependency Caching

**Backend (Python):** `astral-sh/setup-uv` with `enable-cache: true` and `cache-dependency-glob: apps/api/uv.lock`.

**Frontend (Node):** `pnpm/action-setup` (reads `packageManager`), then `actions/setup-node` with `cache: pnpm`.

**Docker:** `cache-from` / `cache-to: type=gha,mode=max`.

#### 5. Test Services

- **Backend:** PostgreSQL + pgvector via a service container (`pgvector/pgvector:pg16`), `DATABASE_URL=postgresql://test:test@localhost:5432/test`. pytest config excludes `live` tests by default.
- **Frontend:** no external services (Vitest + jsdom + MSW).
- **Coverage:** frontend coverage uploaded as an artifact. The backend step is wired for `.coverage` but `pytest-cov` is not a dev dependency yet, so nothing is produced until it is added.

### Alternative Approaches Considered

#### Separate workflow per job (previous design, rejected)
- Eight workflow files: test/lint/build per app plus two deploy workflows
- **Cons:** duplicated setup boilerplate, deploy could not guarantee CI passed on the commit it shipped, `workflow_run` fired once per build workflow and raced on artifacts
- **Why rejected:** one CI workflow with path-filtered jobs keeps parallelism and removes the duplication

#### Auto-deploy to staging on main (rejected)
- **Why rejected:** deploys are a deliberate action. Running CI inside the deploy workflow gives the same safety without auto-triggers.

#### Workflow matrix for Python/Node versions (deferred)
- Single target versions (3.12, Node 22). Add a matrix if multi-version support is needed.

#### Docker build in PRs (rejected)
- Slow (~5-10 min per PR) and the image is discarded. Build runs only on main and deploy.

## Implementation Status

Done:
- [x] `ci.yml` (lint, test, build, path filter on PRs)
- [x] `deploy.yml` (tag guard, reusable CI, environment dropdown)
- [x] GHCR publishing, uv / pnpm / Docker caching, concurrency groups, least-privilege permissions

Remaining:
1. **Configure required status checks** in Settings → Branches → main protection. Check names are `ci / lint-backend`, `ci / test-backend`, `ci / lint-frontend`, `ci / test-frontend`. Jobs skipped by the path filter count as passing.
2. **Create GitHub Environments** `staging` and `production`; add required reviewers to `production`.
3. **Replace the TODO stubs** in `deploy.yml` (deploy, health check, notifications) with real commands. Stubs currently only echo, so a deploy "succeeds" without doing anything.
4. **Add `pytest-cov`** to the backend dev dependencies if coverage reporting is wanted.
5. **Add workflow badge** to README: `https://github.com/<org>/<repo>/actions/workflows/ci.yml/badge.svg`.
6. **Document CI/CD in CONTRIBUTING.md:** local commands that match CI, how to run a deploy (Actions → deploy → Use workflow from → Tags → pick environment).
7. **Slack/email notifications** (optional) in the failure step.

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Deploy ships an untested tag** | `deploy.yml` calls `ci.yml` on the tag first; `deploy` needs `ci` to succeed |
| **Deploy runs from a branch** | `check-ref` job fails unless the ref is a tag |
| **Deploy rebuilds a different image than the one tested on main** | Image is rebuilt from the tagged commit, and CI runs on that exact commit. Tag only commits already green on main. |
| **Stub deploy steps pass without deploying** | Replace stubs before first real use (Remaining #3) |
| **Secrets leak in logs** | GitHub masks secrets. User-controlled values go through `env:`, never interpolated into `run:` |
| **Bad prod deploy** | Health check after deploy; `production` environment requires reviewer approval |
| **CI timeout (tests hang)** | Job-level `timeout-minutes` (10-30 per job) |
| **Skipped jobs satisfy required checks on PRs** | Intended for path-filtered jobs. If a stricter gate is needed, add a final `ci-ok` job that depends on all jobs and require only that |
| **Action major bumps break a workflow** | Verified inputs against each action's `action.yml`; watch the first PR and main runs |

## Test Strategy

### PR-blocking
- **Backend:** `uv run ruff check .`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -v --tb=short` (real PostgreSQL + pgvector service)
- **Frontend:** `pnpm run lint`, `pnpm run typecheck`, `pnpm run test`

### Post-Deploy Verification
- Health check against `/health` (stubbed, to be implemented)
- Error-rate and latency monitoring (e.g. Datadog/New Relic) once available

## Success Checklist

- [ ] `ci` passes on a PR and on main
- [ ] PR checks set as required in branch protection
- [ ] Docker image `main-<sha7>` appears in GHCR after a merge to main
- [ ] `frontend-build` artifact uploaded after a merge to main
- [ ] `deploy` refuses to run from a branch
- [ ] `deploy` from a tag runs CI first, then deploys to the chosen environment
- [ ] `production` requires reviewer approval
- [ ] Deploy stubs replaced with real commands and secrets configured
- [ ] README and CONTRIBUTING.md updated

## Open Questions

- [x] Registry → GHCR
- [ ] How are staging/production deployed? (SSH + docker-compose, Kubernetes, other?)
- [ ] Do staging/production environments already exist, or must they be created?
- [ ] Should frontend artifacts go to a CDN or be served by the backend?
- [ ] Notification preferences for failures? (Slack, email, GitHub only?)
