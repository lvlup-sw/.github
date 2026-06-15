# Design: Org CI Re-Architecture — Composable Reusable Workflows

**Feature ID:** `org-ci-rearchitecture`
**Date:** 2026-06-15
**Primary implementation repo:** `lvlup-sw/.github` (cross-repo) + `lvlup-sw/bifrost` (reference migration)

## Problem Statement

The org's shared CI has drifted into per-repo forks. `lvlup-sw/.github` hosts reusable
workflows (`build-and-test.yml`, `coverage-gate.yml`, `update-baseline.yml`,
`format-check.yml`) and a shared `scripts/ci/coverage-gate.sh`. Three active C# repos
(**strategos, basileus, DataFerry**) consume them; but five hand-roll their CI
(**bifrost, valkyrie, authscript, ares-elite-platform, Ecs.CSharp.Benchmark**), and
**two repos (bifrost + valkyrie) independently forked `coverage-gate.sh`** — bifrost's
fork just diverged further in PR #33 by adding per-assembly + branch gating.

The root cause is structural: the org's *only* reuse primitive is the **reusable
workflow**, which by a hard GitHub constraint **cannot accept caller-injected steps**. So
the moment a repo needs "standard build/test **plus** a repo-specific step" (bifrost's AOT
smoke, benchmark smoke; a stricter gate), it must fork or the org must grow an unbounded
boolean-input surface (the "god-workflow"). Forking is what actually happened.

**Goal:** make the org CI **composable** so every repo consumes shared building blocks
instead of forking — without breaking the three repos already on the org workflows. Per
the scope decision: upstream the per-assembly/branch gate as an **opt-in** capability,
introduce **composite actions** as the composable primitives, rebuild the reusable
workflows on top of them, and migrate **bifrost as the reference consumer** (killing its
fork, adding AOT/benchmark smoke as opt-in org capabilities). Other repos migrate later.

## Options Considered

### Option 1: Composite actions + thin preset workflows (hybrid) — CHOSEN

**Approach:** Author composable **composite actions** (`dotnet-build-test`,
`coverage-gate`, `aot-smoke`, `benchmark-smoke`) as the primitives. Rebuild the reusable
**workflows** as thin presets *implemented via* those actions (single source of truth).
Turnkey repos call a workflow; advanced repos (bifrost) compose actions directly or call a
workflow and add their own `needs:`-chained jobs.

**Pros:**
- Defeats the step-injection ceiling: the caller owns job/step order and interleaves its
  own steps around `uses: …/actions/dotnet-build-test@sha`.
- DRY — workflows built on actions; no duplicated logic; one place to fix.
- bifrost's "extras" become opt-in org capabilities, not forks; valkyrie's fork converges too.

**Cons:**
- More artifacts in `lvlup-sw/.github` (actions + workflows).
- Genuinely a hybrid: composite actions can't declare `matrix`/`services`/job `permissions`,
  so those stay in the caller — two mental models to teach.

**Best when:** a fleet has a shared core but several repos need bespoke extra steps — exactly
this org.

### Option 2: One rich reusable workflow per concern (input-driven "god-workflow")

**Approach:** Keep only reusable workflows; absorb every variation as inputs
(`run-aot-smoke`, `aot-project`, `run-benchmark`, `benchmark-filter`, `gate-mode`,
`gate-metrics`, …).

**Pros:** One `uses:` per repo; simplest possible consumer; no new action concept.

**Cons:** Hits the step-injection ceiling for anything *between* built-in steps; the input
surface grows without bound and every repo's edge case bloats one shared file; ordering of
optional steps is fixed by the workflow author, not the caller.

**Best when:** variation is small and purely parametric (it isn't here — AOT/benchmark are
whole extra steps).

### Option 3: Starter workflow templates (copy-and-own)

**Approach:** Ship `workflow-templates/` that repos copy into their own `.github/workflows`
and customize locally (the org already has one template).

**Pros:** Maximum per-repo flexibility; zero runtime coupling.

**Cons:** **This is the status quo that caused the problem** — every copy is an immediate
fork; bug-fixes/improvements never propagate; divergence is guaranteed (bifrost + valkyrie
prove it).

**Best when:** repos are genuinely heterogeneous with little shared logic — not this org.

**Rationale for Option 1:** only the composite-action hybrid both (a) eliminates the
fork-forcing constraint and (b) keeps a single source of truth. Option 2 re-creates the
maintainability problem in one file; Option 3 *is* the problem.

## Chosen Approach

**Option 1 — composite actions + thin preset workflows (hybrid).** Author the four
composite actions as the composable primitives, rebuild the reusable workflows on top of
them (single source of truth), keep the per-assembly/branch gate **opt-in** behind a
`gate-mode` input so the three existing consumers are untouched, and migrate **bifrost as
the reference consumer** — deleting its forked gate script and proving the AOT/benchmark
extras work as opt-in org capabilities. Other repos (starting with valkyrie's fork) migrate
later, repo-by-repo. This is the only option that removes the fork-forcing GitHub
constraint *and* preserves a single source of truth.

## Technical Design

In `lvlup-sw/.github`:

- **`actions/dotnet-build-test/action.yml`** — composite: restore → `dotnet build -c
  Release` → the existing per-project **MTP** loop (`dotnet run --project … -- --coverage
  --coverage-output-format cobertura …`, already MTP/TUnit-aware) → merge (ReportGenerator)
  → upload `coverage-reports`. Inputs mirror today's `build-and-test.yml`.
- **`actions/coverage-gate/action.yml`** — composite running the shared script. Inputs:
  `threshold`, **`gate-mode` (aggregate|per-project|per-assembly, default `aggregate`)**,
  **`metrics` (line|line+branch, default `line`)**, `exclude`, `output-dir`; posts the PR
  comment.
- **`actions/aot-smoke/action.yml`** (opt-in) — install clang/zlib → `dotnet publish
  /p:PublishAot=true` → run the native binary. Input: `project-path`.
- **`actions/benchmark-smoke/action.yml`** (opt-in) — `dotnet run --project <bench> --
  --job Dry --filter '*'`. Inputs: `benchmark-project`, `filter`.
- **`scripts/ci/coverage-gate.sh`** — upstream bifrost's #33 version (branch gating +
  `--per-project` + `--per-assembly` + `--exclude`) **with the default path unchanged
  (aggregate/line)**. The bash fixture harness comes with it.
- **`workflows/{build-and-test,coverage-gate}.yml`** — rebuilt as thin wrappers over the
  actions; **same inputs/outputs/defaults** as today.

Consumers reference everything by **SHA** (`@<40-char>`), with the org repo cutting
tags (`v1`, …) for human-readable pinning.

## Integration Points

- **Existing consumers (strategos, basileus, DataFerry):** consume `coverage-gate.yml` /
  `build-and-test.yml` today. The refactor must be **behavior-identical at default inputs**
  — they require no change and must not silently shift gate behavior.
- **bifrost (reference migration):** its `ci.yml` is rewritten to call the org
  `dotnet-build-test` + `aot-smoke` + `benchmark-smoke` actions and the `coverage-gate`
  action with `gate-mode: per-assembly, metrics: line+branch`; bifrost's forked
  `scripts/ci/coverage-gate.sh` is deleted.
- **valkyrie:** second fork of `coverage-gate.sh` — converge to the org script (follow-up).
- **`lvlup-sw/.github` self-CI:** new `actions/` need lint (`actionlint`) + a canary
  workflow exercising each action against a fixture .NET repo (or bifrost) on PRs to the org repo.
- **Versioning/pinning:** ties to bifrost #19/DR-1 — centralizing means each repo pins one
  org `@sha` rather than N action refs.

## Blast-Radius / Migration-Impact Analysis (mandated)

| Cohort | Repos | Impact | Mitigation |
|--------|-------|--------|-----------|
| **On org workflows** | strategos, basileus, DataFerry(frozen) | Workflows rebuilt on composite actions. **Risk if default changes.** | Default `gate-mode=aggregate, metrics=line` **unchanged**; behavior-parity test (DR-6); they stay SHA-pinned, so the refactor only reaches them on a deliberate bump. |
| **Forked gate** | bifrost, valkyrie | Local `coverage-gate.sh` deleted; point at org `.shared` script. | bifrost migrates here; valkyrie = tracked follow-up (not in this initiative). |
| **Hand-rolled** | authscript, ares-elite-platform, Ecs.CSharp.Benchmark | **None now** — not touched. | Future opt-in migration once the pattern is proven. |
| **No CI** | dynatoi, bronze-age | None. | n/a. |
| **Org repo** | `lvlup-sw/.github` | New `actions/`, script upgrade, workflow refactor. | Self-CI + canary; tag a release. |

**Rollback:** every consumer is SHA-pinned, so reverting is "pin to the previous SHA" — no
code change, instant. The single highest-risk change (the shared gate script) keeps its
default path byte-compatible, verified by the fixture harness's aggregate cases.

## Testing Strategy

- **Shared gate script (DR-1):** the bifrost bash fixture harness travels with the script
  to `lvlup-sw/.github`; it exercises aggregate (default), per-project, per-assembly, branch,
  `--exclude`, mutual-exclusion, no-vacuous-pass, and both the `xmllint` and grep/sed paths.
  A dedicated **backward-compat case** asserts a default `--coverage-file … --threshold N`
  run is byte-identical (verdict + PR comment) to the pre-change script.
- **Composite actions (DR-2/3/4):** a **canary workflow** in `lvlup-sw/.github`, triggered on
  PRs to that repo, runs each action against a small fixture .NET project (and/or bifrost as
  the live canary): `dotnet-build-test` produces the coverage artifact; `coverage-gate` passes
  at default and fails a seeded sub-threshold assembly under `per-assembly`; `aot-smoke` and
  `benchmark-smoke` succeed when invoked and are absent otherwise. `actionlint` gates all YAML.
- **Behavior parity (DR-6):** before any consumer bump, the parity guard demonstrates
  strategos/basileus see identical results — protecting `main` on repos this initiative does
  not otherwise touch.
- **bifrost migration (DR-5):** bifrost's full CI must stay green end-to-end after switching to
  org refs — build, tests, AOT smoke, benchmark smoke, and the per-assembly+branch gate across
  all 9 shipping assemblies — with the local fork removed.

## Requirements

### DR-1 — Upstream the configurable gate into the org shared script

Replace `lvlup-sw/.github/scripts/ci/coverage-gate.sh` with bifrost's #33 version: branch
gating, `--per-project`, `--per-assembly`, `--exclude`/`EXCLUDE` — **default invocation
(`--coverage-file … --threshold N`) unchanged (aggregate, line-only)**. Bring the bash
fixture harness.

**Acceptance criteria:**
- `bash scripts/ci/coverage-gate.test.sh` passes in `lvlup-sw/.github` (all aggregate +
  per-project + per-assembly + branch + exclude + xmllint/fallback cases).
- A default `--coverage-file <x> --threshold 80` run produces **byte-identical pass/fail +
  PR-comment** to the pre-change script for the same input (backward-compat lock).
- **Failure mode:** an empty/all-excluded assembly set exits non-zero (no vacuous pass).

### DR-2 — `coverage-gate` composite action + rebuilt `coverage-gate.yml`

Add `actions/coverage-gate/action.yml` exposing `threshold`, `gate-mode` (default
`aggregate`), `metrics` (default `line`), `exclude`, `output-dir`. Rebuild
`workflows/coverage-gate.yml` to call it, preserving its current inputs/defaults.

**Acceptance criteria:**
- A consumer pinned to the new ref with **no input changes** gets identical behavior
  (aggregate/line) — verified against a fixture repo.
- `gate-mode: per-assembly, metrics: line+branch` reproduces bifrost's per-assembly gate.
- `actionlint` clean.

### DR-3 — `dotnet-build-test` composite action + rebuilt `build-and-test.yml`

Extract today's `build-and-test.yml` steps into `actions/dotnet-build-test/action.yml`
(restore/build/MTP-test/merge/upload); rebuild the workflow as a thin wrapper.

**Acceptance criteria:**
- Behavior parity for a current consumer (same artifacts, same `tests-passed` output).
- The MTP `dotnet run --project … --coverage` loop and `skip-patterns` are preserved.

### DR-4 — `aot-smoke` + `benchmark-smoke` opt-in composite actions

Add the two actions reproducing bifrost's native-publish-and-run and BenchmarkDotNet dry
run.

**Acceptance criteria:**
- Invoked, they reproduce bifrost's current AOT (DR-13) and benchmark smoke behavior.
- Absent from a caller, they have zero effect (opt-in; no-op by omission).

### DR-5 — Migrate bifrost as the reference consumer

Rewrite bifrost `ci.yml` to consume the org actions/workflows (build-test, aot-smoke,
benchmark-smoke, coverage-gate `per-assembly`); **delete bifrost's forked
`scripts/ci/coverage-gate.sh`**; pin all org refs to SHA.

**Acceptance criteria:**
- bifrost CI green: build, tests, AOT smoke, benchmark smoke, **per-assembly+branch gate
  (all 9 assemblies ≥80%)**.
- bifrost's local `coverage-gate.sh` + harness removed (or reduced to a thin pin);
  no remaining fork.
- Every org `uses:` is a 40-char SHA (consistent with #19).

### DR-6 — Versioning, backward-compat guard, and rollback (failure modes)

Tag `lvlup-sw/.github` (`v1`); document consumer pinning + a migration guide; add the
behavior-parity guard for default-mode consumers; record valkyrie fork-removal as a
follow-up.

**Acceptance criteria:**
- A tagged release exists; consumers can pin `@<sha>` or `@v1`.
- **Backward-compat:** a CI check (or documented manual gate) proves strategos/basileus
  behavior is unchanged before any bump reaches them.
- **Rollback:** documented "pin to previous SHA" revert path, tested once.
- Follow-up issue filed for valkyrie's fork convergence + the remaining hand-rolled repos.

## Risks

- **Silent gate-behavior shift** for existing consumers — *the* load-bearing risk; mitigated
  by unchanged defaults + the byte-compat acceptance on DR-1/DR-2 + SHA pinning.
- **Composite-action limitations** (no matrix/services) surface late — keep those in callers;
  document the hybrid boundary.
- **Cross-repo coordination** — changes land in `lvlup-sw/.github` first (tagged), then
  bifrost bumps to the tag; the two PRs are sequenced, not simultaneous.

## Open Questions

1. **Pin to `@v1` tag vs. `@sha`** for consumers — SHA is strongest (supply-chain), tags are
   friendlier with Dependabot. *(Default: SHA, Dependabot-managed.)*
2. **Should `format-check.yml` / `update-baseline.yml` also be re-based on composite actions
   now**, or only build-test + coverage-gate this round? *(Default: only the two in scope;
   others follow the same pattern later.)*
3. **Where does the design doc live** — this initiative's PRs target `lvlup-sw/.github`;
   mirror this doc there on first PR. *(Default: yes, copy to the org repo.)*
