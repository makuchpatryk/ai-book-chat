# GitHub Actions CI/CD Implementation Plan

## Summary
Automate testing, linting, type-checking, building, and deploying for a Python/TypeScript monorepo (FastAPI backend + React frontend). Catch bugs early, enforce code quality, and reduce manual deployment overhead.

## Success Criteria
- All PRs run linting, type-check, and tests before review
- Tests and checks pass 100% before merge to main (required status checks)
- Build artifacts published on main merge
- Deployments automated for staging/production on main push
- CI run time <10 minutes per workflow
- Zero manual deployment steps for routine releases

## Scope & Constraints
- **In scope:** PR checks (test, lint, type-check), build on merge, deploy to staging/production, Docker image publishing
- **Out of scope:** Cross-browser testing, load testing, security scanning (can add later)
- **Hard constraints:** Must work with existing Turbo, uv, pnpm setup; no changes to local dev workflow
- **Trade-offs:** Separate workflows per app (frontend/backend) for clarity and speed over single monolithic workflow; caching via GitHub Actions cache and Docker layer caching for performance

## Architecture & Design

### High-Level Flow
```
PR opened/updated
  ├─→ [test-backend] Run pytest (unit + integration)
  ├─→ [test-frontend] Run Vitest
  ├─→ [lint-backend] Ruff check, MyPy typecheck
  └─→ [lint-frontend] ESLint, TypeScript check

All pass? → Allow merge to main

On main push
  ├─→ [build-backend] Build Docker image → push to registry
  ├─→ [build-frontend] Build static assets
  └─→ [deploy-staging] Deploy to staging (automatic)

Manual trigger or tag
  └─→ [deploy-production] Deploy to production (manual or on tag)
```

### Key Changes

#### 1. Workflow Files (new, in `.github/workflows/`)

| File | Purpose | Trigger |
|------|---------|---------|
| `test-backend.yml` | pytest on backend code changes | PR, push to main |
| `test-frontend.yml` | Vitest on frontend code changes | PR, push to main |
| `lint-backend.yml` | Ruff + MyPy + import-linter on backend | PR, push to main |
| `lint-frontend.yml` | ESLint + TypeScript check on frontend | PR, push to main |
| `build-backend.yml` | Docker build and push to registry | Push to main, manual |
| `build-frontend.yml` | Build React artifacts and upload | Push to main, manual |
| `deploy-staging.yml` | Deploy to staging environment | Automatic after build-backend/build-frontend |
| `deploy-production.yml` | Deploy to production | Manual trigger (workflow_dispatch) or on release tag |

#### 2. Environment & Secrets Configuration

**Required GitHub repository secrets:**
- `DOCKER_USERNAME` — Docker Hub or registry username
- `DOCKER_PASSWORD` — Docker Hub or registry password
- `STAGING_DEPLOY_KEY` — SSH key or API token for staging deploy
- `PROD_DEPLOY_KEY` — SSH key or API token for prod deploy
- `DATABASE_URL_STAGING` — Staging database connection string
- `DATABASE_URL_PROD` — Production database connection string
- `REDIS_URL_STAGING` — Staging Redis URL
- `REDIS_URL_PROD` — Production Redis URL
- `LLM_API_KEY` — API key for LLM service (if environment-specific)
- (other env vars as needed)

**Required Actions:**
- `actions/checkout@v4` — Check out code
- `actions/setup-python@v5` — Set up Python
- `actions/setup-node@v4` — Set up Node.js
- `actions/cache@v4` — Cache dependencies (pip, npm)
- `docker/setup-buildx-action@v3` — Docker buildx for multi-arch builds (optional)
- `docker/login-action@v3` — Login to Docker registry
- `docker/build-push-action@v5` — Build and push Docker images

#### 3. Dependency Caching Strategy

**Backend (Python):**
- Cache `uv.lock` → `/root/.cache/uv` (uv's cache dir)
- Key: `uv-${{ runner.os }}-${{ hashFiles('apps/api/uv.lock') }}`

**Frontend (Node):**
- Cache `pnpm-lock.yaml` → `~/.pnpm-store`
- Key: `pnpm-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}`

#### 4. Test Database & Services

**For backend tests:**
- Use testcontainers or Docker Compose in CI, OR
- Use SQLite in-memory database for unit tests (faster, no DB needed)
- Run integration tests against real PostgreSQL container (spawned by test action)

**For frontend tests:**
- No external services needed (Vitest + jsdom + MSW mocks handle it)

### Alternative Approaches Considered

#### Option A: Single Monolithic Workflow (rejected)
- One workflow runs all tests, lint, build, deploy
- **Pros:** Single YAML file to maintain
- **Cons:** 
  - Slower feedback (frontend changes wait for backend tests to finish)
  - Harder to parallelize
  - Single point of failure
- **Why rejected:** Monorepo has independent apps; parallel workflows are faster

#### Option B: Separate Workflows per App (chosen)
- Dedicated workflows for backend and frontend (test, lint, build)
- Deploy workflows depend on successful builds
- **Pros:**
  - Fast parallel execution
  - Clear failure attribution (if frontend tests fail, backend isn't blocked)
  - Easy to disable/modify one app's CI without affecting the other
  - Scales well as monorepo grows
- **Why chosen:** Matches app independence; 30-50% faster CI time vs single workflow

#### Option C: Workflow Matrix for Python/Node Versions (deferred)
- Test against Python 3.10, 3.11, 3.12 and Node 18, 20, 22
- **Pros:** Catches compatibility issues early
- **Cons:** 3x longer CI time, overkill for single-target deployment
- **Why deferred:** Start with single versions (3.12, Node 20), add matrix later if multi-version support is needed

#### Option D: Docker Build in PR (rejected)
- Build Docker image in every PR to catch build errors early
- **Pros:** Catches Dockerfile issues before merge
- **Cons:**
  - Slow (~5-10 min per PR)
  - Doubles CI runtime
  - Image is discarded (not used unless merged)
- **Why rejected:** Build only on main; test suite is sufficient validation for PRs

## Implementation Steps

### Phase 1: PR Checks (Tests & Lint)

1. **Create `.github/workflows/test-backend.yml`**
   - Trigger: `on: [pull_request, push: {branches: [main]}]`
   - Steps: checkout, setup Python, cache uv deps, install deps, run pytest with coverage
   - Artifacts: Upload coverage report to artifacts (optional)

2. **Create `.github/workflows/test-frontend.yml`**
   - Trigger: `on: [pull_request, push: {branches: [main]}]`
   - Steps: checkout, setup Node, cache pnpm deps, install deps, run `pnpm run test`
   - Artifacts: Upload coverage report

3. **Create `.github/workflows/lint-backend.yml`**
   - Trigger: `on: [pull_request, push: {branches: [main]}]`
   - Steps: checkout, setup Python, cache uv, run `uv run ruff check`, `uv run mypy src`, `uv run lint-imports`
   - Config: Report results as inline comments on PR (via action or native GitHub annotations)

4. **Create `.github/workflows/lint-frontend.yml`**
   - Trigger: `on: [pull_request, push: {branches: [main]}]`
   - Steps: checkout, setup Node, cache pnpm, run `pnpm run lint`, `pnpm run typecheck`

5. **Configure required status checks in GitHub repo settings**
   - Go to Settings → Branches → main branch protection rules
   - Require: test-backend, test-frontend, lint-backend, lint-frontend to pass before merge
   - Allow dismissal only by PR author or admins

### Phase 2: Build on Main Merge

6. **Create `.github/workflows/build-backend.yml`**
   - Trigger: `on: [push: {branches: [main]}, workflow_dispatch]`
   - Steps:
     - Checkout
     - Set up Docker buildx
     - Login to Docker registry (Docker Hub or internal)
     - Build and push Docker image: `docker.io/your-org/ai-book-chat-api:latest` and tag with commit SHA
     - Tag as `stable` if desired
   - Output: Image URL for deploy workflow to reference

7. **Create `.github/workflows/build-frontend.yml`**
   - Trigger: `on: [push: {branches: [main]}, workflow_dispatch]`
   - Steps: checkout, setup Node, cache pnpm, build (`pnpm run build`), upload artifacts
   - Output: Frontend static assets (upload to GitHub artifacts, or directly to CDN/S3)

### Phase 3: Deploy

8. **Create `.github/workflows/deploy-staging.yml`**
   - Trigger: `on: workflow_run: {workflows: [build-backend, build-frontend], types: [completed]}`
   - Only run if both builds succeeded
   - Steps:
     - Download Docker image SHA from build-backend artifact
     - SSH into staging server and pull new image
     - Run docker-compose up or kubectl apply (depends on infrastructure)
     - Run smoke tests or health checks to verify deployment

9. **Create `.github/workflows/deploy-production.yml`**
   - Trigger: `on: [workflow_dispatch, push: {tags: ['v*']}]` (manual + on git tag)
   - Manual input: Choose version/commit to deploy (from dropdown)
   - Steps: Same as staging, but to prod infrastructure
   - Safety: Require approval before deploy (GitHub environment protection rule)

### Phase 4: Polish & Documentation

10. **Add workflow badges to README**
    - Display status of main branch CI/CD
    - Example: `![Tests](https://github.com/org/repo/workflows/test-backend/badge.svg)`

11. **Document CI/CD in CONTRIBUTING.md**
    - How to run tests locally (match CI commands)
    - How to manually trigger workflows
    - Troubleshooting guide (e.g., "If Docker build fails...")

12. **Set up Slack/email notifications (optional)**
    - Notify on workflow failure to #dev or team email
    - Can use `8398db/action-slack` or native GitHub notifications

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Docker build fails silently, prod deploy uses stale image** | Include build-backend pass as required status check; deploy workflow only triggers on successful build artifact |
| **Tests pass locally but fail in CI** | Ensure CI environment matches local (same Python, Node versions). Use Docker container for consistent environment. |
| **Secrets leak in logs** | Use GitHub Actions masking (automatically masks secrets in logs). Audit workflow files to avoid echoing env vars. |
| **Deploy takes down staging/prod** | Run health checks post-deploy; if fail, rollback to previous image. Staging deploys automatically; production requires manual approval. |
| **CI timeout (tests hang)** | Set timeout on each job (30 min default; reduce to 15 min per workflow). Add test timeouts (pytest -v --tb=short with timeout plugin). |
| **Database state pollution between test runs** | Use fresh test DB per run (testcontainers or in-memory SQLite for unit tests). Separate integration test DB. |

## Test Strategy

### Unit Tests (PR-blocking)
- **Backend:** pytest unit tests in `apps/api/tests/` (mock external deps)
  - Command: `uv run pytest -m unit` (~30 sec)
- **Frontend:** Vitest component tests in `apps/web/src/` (MSW mocks API)
  - Command: `pnpm run test` (~10 sec)

### Integration Tests (PR-blocking)
- **Backend:** pytest integration tests against real PostgreSQL in Docker
  - Command: `uv run pytest -m integration` (~60 sec, spawns postgres container)
- **Frontend:** E2E tests (optional, can add Playwright later)

### Linting & Type-Checking (PR-blocking)
- **Backend:** `uv run ruff check`, `uv run mypy src`, `uv run lint-imports`
- **Frontend:** `pnpm run lint`, `pnpm run typecheck`

### Post-Deploy Verification
- Smoke tests: Check `/health` endpoint returns 200
- Datadog/New Relic alerts: Monitor error rates, latency post-deploy

## Success Checklist

At launch, verify:
- [ ] All 8 workflows created and passing on main branch
- [ ] PR checks required in branch protection settings
- [ ] Docker images building and pushed to registry on main merge
- [ ] Staging deploys automatically after successful builds
- [ ] Production deployment manual but functional (tested with manual trigger)
- [ ] Secrets configured in GitHub repo settings (test with dummy values if needed)
- [ ] README and CONTRIBUTING.md updated with CI/CD docs
- [ ] Developers can run local `pytest` and `pnpm test` matching CI commands

## Timeline & Estimates

- **Phase 1 (PR Checks):** ~1-2 hours
  - Write 4 workflows (test-backend, test-frontend, lint-backend, lint-frontend)
  - Test locally, iterate on caching/timeouts
- **Phase 2 (Build):** ~1-2 hours
  - Write build-backend and build-frontend workflows
  - Set up Docker registry login and artifact upload
- **Phase 3 (Deploy):** ~2-4 hours
  - Write deploy-staging and deploy-production workflows
  - Set up SSH keys, environment vars, health checks
  - Manual testing on staging
- **Phase 4 (Polish):** ~30-45 min
  - Update README, CONTRIBUTING.md, add badges
- **Total:** ~5-9 hours (rough estimate; adjust based on infrastructure complexity)

**Blocking factors:** Access to staging/prod infrastructure, Docker registry credentials, SSH keys for deployment.

## Open Questions

- [ ] Where should Docker images be pushed? (Docker Hub, GitHub Container Registry, private ECR?)
- [ ] How is staging/production currently deployed? (Manual SSH + docker-compose, Kubernetes, serverless?)
- [ ] Are there existing staging/production environments, or do they need to be created?
- [ ] Should frontend artifacts go to CDN (Netlify, Vercel, S3) or be served by backend?
- [ ] Any notification preferences for CI failures? (Slack, email, GitHub only?)
- [ ] Should production deploys require manual approval via GitHub environments?
