# Design: CodeQL + Dependency-Review reusable workflows

**Driver:** `lvlup-sw/hierophant` epic #1 (paved road), Phase 2 remainder (#13). Spike for Phase 3 (#14) — the `LevelUp.Templates` scaffolded `ci.yml` must reference real org reusables.
**Source design (consumer side):** `hierophant/docs/designs/2026-06-20-levelup-templates.md` (D1, DR-1…DR-6).

## Problem
`lvlup-sw/.github` hosts the org's reusable CI suite (`build-and-test.yml`, `coverage-gate.yml`, `format-check.yml`, `node-build-test.yml`, `update-baseline.yml`), each with a composite-action backing and a `canary-*` self-test. **CodeQL and dependency-review are missing** — they still live inline in `hierophant` (`codeql.yml`, the `ci.yml` `dependency-review` job), explicitly flagged there as "the reference to promote once a second repo needs it" (stack-seed §7.3 gap #3). Phase 3 is that second consumer.

## Chosen approach
Two thin `workflow_call` PRESET workflows over the upstream actions — matching the repo's existing wrapper convention (logic in the action, workflow owns only runs-on + the call signature + least-privilege perms). CodeQL needs no composite (it is already action-driven); a thin reusable is sufficient.

- **`codeql.yml`** — buildless by default (`build-mode: none`), `languages` default `csharp`. Caller owns event triggers (push/pull_request/schedule) and any `GHAS_ENABLED` gating. `upload`/`upload-database` are passthrough so canaries can run without Code Scanning enabled. Actions SHA-pinned to the refs hierophant already proved (`github/codeql-action@dd903d2e` v3).
- **`dependency-review.yml`** — wraps `actions/dependency-review-action@2031cfc0` (v4), `fail-on-severity` default `high`. PR-event only (the action diffs base..head); caller owns the `pull_request` trigger + gating. License allow/deny deferred to Phase 5.

## Canaries (self-test)
- **`canary-codeql.yml`** — calls the reusable on its PR ref with `csharp` + `build-mode: none` against `scripts/ci/testdata/csharp-canary-fixture/`, `upload: never`, `upload-database: false`. Green job = the buildless path runs. No Code Scanning enablement required.
- **`canary-dependency-review.yml`** — calls the reusable on a real PR; dependency review is available on this public repo without GHAS, so a workflow-only PR (no vulnerable deps added) passes.

## Versioning / rollout
Merge to `main`, then move the moving `v1` tag (and cut `v1.3`) to the merge commit so `@v1` consumers (starting with hierophant) receive codeql/dependency-review. Renovate keeps the action pins current.

## Consumer wiring (hierophant, separate PR)
hierophant replaces its inline `codeql.yml` + `ci.yml` `dependency-review` job with `uses:` calls to these reusables, SHA-pinned `# v1`, preserving its `vars.GHAS_ENABLED` gate, weekly CodeQL schedule, and PR-scoped dependency review. Its `scripts/verify-ci-workflows.sh` contract follows the logic to its new home.
