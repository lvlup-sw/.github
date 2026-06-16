# Org CI: Consumer Pinning & Migration Guide

**Applies to:** `lvlup-sw/.github` composite CI layer, `v1` and later.
**Design / plan:** `docs/designs/2026-06-15-org-ci-rearchitecture.md`,
`docs/plans/2026-06-15-org-ci-rearchitecture.md`.

The org now ships CI as **composable building blocks**: four composite actions
plus two thin preset reusable workflows built on top of them. This guide is for
repos that consume them — how to pin a version, which building block to use, and
how to opt into the stricter coverage gate.

For the safe-bump and revert procedure, see
`docs/runbooks/org-ci-parity-and-rollback.md`.

## What's available at `v1`

| Building block | Path | Use it when |
|----------------|------|-------------|
| `build-and-test.yml` (reusable workflow) | `.github/workflows/build-and-test.yml` | Turnkey: restore → build → MTP test → merge coverage → upload `coverage-reports`. |
| `coverage-gate.yml` (reusable workflow) | `.github/workflows/coverage-gate.yml` | Turnkey: download `coverage-reports`, enforce a threshold, post the PR comment. |
| `dotnet-build-test` (composite action) | `actions/dotnet-build-test` | Compose build/test into your own job, interleaving extra steps. |
| `coverage-gate` (composite action) | `actions/coverage-gate` | Run the shared gate script with full control over mode/metrics. |
| `aot-smoke` (composite action, opt-in) | `actions/aot-smoke` | NativeAOT publish-and-run smoke. |
| `benchmark-smoke` (composite action, opt-in) | `actions/benchmark-smoke` | BenchmarkDotNet `--job Dry` smoke. |

**Workflow vs action:** use a **reusable workflow** when the org-standard job is
all you need (one `uses:` line). Use the **composite actions** when you need to
add your own steps *around* the standard ones — the GitHub reusable-workflow
model cannot accept caller-injected steps, which is the whole reason the actions
exist. Composite actions also can't declare `matrix` / `services` / job-level
`permissions`; those stay in your caller workflow.

## Pinning

Pin every org `uses:` to an **immutable ref**. Two options:

- **`@v1` (tag)** — human-readable, friendly with the bump bot. Recommended for
  most repos.
- **`@<40-char SHA>` (commit)** — strongest supply-chain guarantee (a tag can be
  moved; a SHA cannot). Recommended for security-sensitive repos.

Both resolve to the same release. **Never pin `@main`** — it floats and defeats
reproducibility.

```yaml
# Reusable workflow — pin the workflow file:
jobs:
  test:
    uses: lvlup-sw/.github/.github/workflows/build-and-test.yml@v1
    with:
      solution-path: MyProject.slnx
      test-project-patterns: |
        **/tests/**/*.Tests.csproj

  coverage:
    needs: test
    uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@v1
    with:
      coverage-threshold: 90
```

```yaml
# Composite action — pin the action:
steps:
  - uses: actions/checkout@v4
  - uses: lvlup-sw/.github/actions/dotnet-build-test@v1
    with:
      solution-path: MyProject.slnx
      test-project-patterns: |
        **/tests/**/*.Tests.csproj
```

### Pinning the shared gate script

The `coverage-gate` **action** sparse-checks-out the shared
`scripts/ci/coverage-gate.sh` at its `shared-ref` input (default `main`). The
`coverage-gate.yml` **workflow** pins `shared-ref` to the release for you, so
workflow consumers get a fully pinned graph automatically.

If you compose the `coverage-gate` **action directly**, pin `shared-ref` to the
same ref as the action — otherwise the script floats on `main`:

```yaml
  - uses: lvlup-sw/.github/actions/coverage-gate@v1
    with:
      threshold: 80
      gate-mode: per-assembly
      shared-ref: v1   # pin the script too
```

### Staying current

Action pins in **this org repo** are bumped by **Dependabot**
(`.github/dependabot.yml`). In **your** repo, add a `github-actions` Dependabot
(or Renovate) entry so your pins to `@v1`/`@<sha>` get update PRs as the org cuts
new releases. Don't run both bots against the same `uses:` refs.

## Coverage gate: defaults and opt-in

The gate's **default is unchanged** from the pre-refactor org script:
`gate-mode: aggregate`, `metrics: line`. Existing consumers
(strategos / basileus / DataFerry) pin `@v1` and get **byte-identical** behavior
— no input changes needed. (This is locked by a backward-compat parity test on
the shared script and the default-parity canary; see the runbook.)

Opt into stricter gating per repo:

| Input | Values | Effect |
|-------|--------|--------|
| `gate-mode` | `aggregate` (default), `per-project`, `per-assembly` | Granularity the threshold is applied at. |
| `metrics` | `line` (default), `line+branch` | Aggregate mode: also gate branch coverage. |
| `exclude` | whitespace-separated globs | Skip named projects / assemblies. |

```yaml
# bifrost-style strict gate: every assembly ≥ 80% line AND branch
  coverage:
    uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@v1
    with:
      coverage-threshold: 80
      gate-mode: per-assembly
      metrics: line+branch
```

Failure modes are non-vacuous: an empty or fully-excluded unit set exits
non-zero rather than passing silently.

## Opt-in smoke actions

Both are **no-ops by omission** — a repo that never references them is
unaffected.

```yaml
  - uses: lvlup-sw/.github/actions/aot-smoke@v1
    with:
      project-path: samples/MyApp.AotSmoke/MyApp.AotSmoke.csproj

  - uses: lvlup-sw/.github/actions/benchmark-smoke@v1
    with:
      benchmark-project: src/MyApp.Benchmarks/MyApp.Benchmarks.csproj
```

## Migration paths by repo

- **Already on the org workflows** (strategos, basileus, DataFerry): change the
  ref from `@main`/`@<old-sha>` to `@v1`. No input or behavior change. Confirm
  via the parity runbook before merging.
- **Forked the gate script** (valkyrie): delete the local
  `scripts/ci/coverage-gate.sh` fork and call the `coverage-gate` action (or
  workflow) instead. Pick `gate-mode`/`metrics` to match your fork's behavior.
- **Hand-rolled C# CI** (authscript, ares-elite-platform, Ecs.CSharp.Benchmark):
  replace bespoke build/test/coverage steps with `dotnet-build-test` +
  `coverage-gate`; add `aot-smoke` / `benchmark-smoke` only if you need them.
- **Reference consumer** (bifrost): see `lvlup-sw/bifrost#39` — composes all four
  actions including the per-assembly + branch gate.

## TypeScript / Node consumers (`v1.1`+)

The TS layer mirrors the C# one: a `node-build-test` action (+ a
`node-build-test.yml` preset) and an opt-in `node-benchmark-smoke`. **The gate is
the same** — `coverage-gate` consumes the generic Cobertura `node-build-test`
emits, so there is no TS-specific gate.

```yaml
jobs:
  ci:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - uses: lvlup-sw/.github/actions/node-build-test@v1.1
        with:
          working-directory: .
          lint-command: 'eslint .'   # opt-in; omit to skip lint
      # Consume the gate as an ACTION on the produced report — NOT the
      # coverage-gate.yml workflow (that merges via .NET ReportGenerator).
      - uses: lvlup-sw/.github/actions/coverage-gate@v1.1
        with:
          coverage-file: ./coverage-reports/Cobertura.xml
          threshold: 80
          shared-ref: v1.1
```

Or turnkey via the preset (then add a gate job):
`uses: lvlup-sw/.github/.github/workflows/node-build-test.yml@v1.1`.

Notes:

- **Coverage provider package required.** vitest needs `@vitest/coverage-v8`
  (default) or `@vitest/coverage-istanbul` installed to emit Cobertura. The action
  passes `--coverage.reporter=cobertura`; set `coverage-provider: istanbul` for the
  instrumented TSX/JSX fallback.
- **Package manager** is auto-detected from the lockfile (npm / pnpm / bun); set
  `package-manager` to force it. **Lint** is opt-in (`lint-command`, default off).
- **Monorepos:** `node-build-test` merges every project's Cobertura into one
  `coverage-reports/Cobertura.xml` (via the shared `scripts/ci/merge-cobertura.mjs`),
  so the `aggregate` default works across all projects.
- **Gating granularity.** istanbul names each Cobertura `<package>` by **source
  directory**, not assembly — so `gate-mode: per-assembly` gates **per-directory**
  for TS (same mechanism, different unit). `--exclude` matches the directory name.
- Pin `@v1.1`/`@<sha>` and let Dependabot bump it, same as the C# blocks.
