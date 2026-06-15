# Implementation Plan: Org CI Re-Architecture

**Design:** `docs/designs/2026-06-15-org-ci-rearchitecture.md`
**Feature ID:** `org-ci-rearchitecture`
**Date:** 2026-06-15

## ⚠️ Cross-repo execution note (read before delegation)

This plan spans **two repositories**:
- **`lvlup-sw/.github`** — tasks 1–10, 13–15 (composite actions, shared script, workflow
  rebuilds, self-CI, tagging). **Not checked out in this (bifrost) working tree.**
- **`lvlup-sw/bifrost`** — tasks 11–12 (reference migration).

The exarchos delegate phase creates worktrees in the *current* repo, so it **cannot run
this plan as-is**. At plan-review, decide the execution model: (a) clone `lvlup-sw/.github`
and run that repo's tasks there (separate exarchos run or manual), then bump bifrost; or
(b) hand-execute the org-repo PR and use exarchos only for the bifrost migration. The org
PR **must land + be tagged (task-13) before** the bifrost migration (task-11) — bifrost
pins to the org tag/SHA.

## TDD shape

This is CI infrastructure (YAML + bash). The "failing test first" maps to: **bash fixture
harness** for the gate script (genuine RED→GREEN), **`actionlint`** + a **canary workflow**
for composite actions/workflows (`[VERIFY]`), and **green end-to-end CI** for the bifrost
migration (`[VERIFY]`). No classic unit tests apply.

## Traceability

| DR | Requirement | Tasks | Repo |
|----|-------------|-------|------|
| DR-1 | Upstream configurable gate into shared script | 1 | .github |
| DR-2 | `coverage-gate` action + rebuilt workflow | 2, 3, 4 | .github |
| DR-3 | `dotnet-build-test` action + rebuilt workflow | 5, 6, 7 | .github |
| DR-4 | `aot-smoke` + `benchmark-smoke` actions | 8, 9, 10 | .github |
| DR-5 | Migrate bifrost (reference consumer) | 11, 12 | bifrost |
| DR-6 | Versioning, backward-compat guard, rollback | 13, 14, 15 | .github |

---

## Group A — Shared gate script (DR-1, repo: `lvlup-sw/.github`)

### Task 1: Upstream the configurable gate + backward-compat lock
**Phase:** RED → GREEN → VERIFY

1. [RED] Add a **backward-compat parity** case to the bash harness: capture the *current*
   org `scripts/ci/coverage-gate.sh` output (verdict + `pr-comment.md`) for a fixture at
   `--coverage-file … --threshold 80`, then assert the *new* script produces byte-identical
   output. Against today's org script this case is moot; it RED-guards the replacement.
   - File: `scripts/ci/coverage-gate.test.sh` (ported from bifrost #33).
2. [GREEN] Replace `scripts/ci/coverage-gate.sh` with bifrost's version (branch gating +
   `--per-project` + `--per-assembly` + `--exclude`), **default path unchanged
   (aggregate/line)**. Bring all fixtures from `scripts/ci/testdata/`.
3. [VERIFY] `bash scripts/ci/coverage-gate.test.sh` passes (all modes + parity + xmllint/
   fallback); empty/all-excluded → non-zero (no vacuous pass).

**Dependencies:** None. **Parallelizable:** No (foundation for Group B). **testingStrategy:** script-fixture.

---

## Group B — `coverage-gate` action + workflow (DR-2, repo: `lvlup-sw/.github`)

### Task 2: `coverage-gate` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] `actions/coverage-gate/action.yml` (composite): inputs `threshold`,
   `gate-mode` (default `aggregate`), `metrics` (default `line`), `exclude`, `output-dir`;
   sparse-checkout the shared `scripts/ci`, run the script with the mapped flags, post the
   PR comment. Map `gate-mode`→`--coverage-file|--per-project|--per-assembly`.
2. [VERIFY] `actionlint` clean; a unit canary step runs the action against a fixture
   cobertura at default (aggregate/line) and at `per-assembly`/`line+branch`.

**Dependencies:** Task 1. **Parallelizable:** No.

### Task 3: Rebuild `coverage-gate.yml` on the action
**Phase:** GREEN → VERIFY
1. [GREEN] Rewrite `workflows/coverage-gate.yml` to call `actions/coverage-gate`, keeping
   its **current inputs + defaults** (coverage-threshold, dotnet-version, runner). Expose a
   pass-through `gate-mode`/`metrics` input (default aggregate/line).
2. [VERIFY] Inputs/outputs match the prior workflow signature (no consumer change needed).

**Dependencies:** Task 2. **Parallelizable:** No.

### Task 4: Default-parity + opt-in canary for the gate
**Phase:** VERIFY
1. [VERIFY] Canary workflow: a default-input call yields the same verdict/comment as the
   old workflow on a fixed cobertura; a `per-assembly` call fails a seeded sub-threshold
   assembly. Record both in the canary run.

**Dependencies:** Task 3. **Parallelizable:** No. **testingStrategy:** canary-integration.

---

## Group C — `dotnet-build-test` action + workflow (DR-3, repo: `lvlup-sw/.github`)

Parallel with Group B (disjoint files).

### Task 5: `dotnet-build-test` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] Extract today's `build-and-test.yml` steps into
   `actions/dotnet-build-test/action.yml`: restore → `dotnet build -c Release` → the
   per-project **MTP** loop (`dotnet run --project … -- --coverage …`) with `skip-patterns`
   → ReportGenerator merge → upload `coverage-reports`. Inputs mirror the workflow's.
2. [VERIFY] `actionlint` clean; the MTP loop + skip-patterns are byte-preserved.

**Dependencies:** None. **Parallelizable:** Yes (with Group B).

### Task 6: Rebuild `build-and-test.yml` on the action
**Phase:** GREEN → VERIFY
1. [GREEN] Thin wrapper calling `actions/dotnet-build-test`; preserve inputs (solution-path,
   test-project-patterns, skip-patterns, coverage-filters, runner, dotnet-version/quality)
   and the `tests-passed` output.
2. [VERIFY] Signature parity with the prior workflow.

**Dependencies:** Task 5. **Parallelizable:** No (after 5).

### Task 7: Build-test parity canary
**Phase:** VERIFY
1. [VERIFY] Canary runs the rebuilt workflow against a fixture .NET repo (or bifrost):
   identical artifact (`coverage-reports`) + `tests-passed` output vs. the prior workflow.

**Dependencies:** Task 6. **Parallelizable:** No.

---

## Group D — opt-in smoke actions (DR-4, repo: `lvlup-sw/.github`)

Parallel with Groups B/C.

### Task 8: `aot-smoke` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] `actions/aot-smoke/action.yml`: install clang/zlib → `dotnet publish
   /p:PublishAot=true` → run the native binary. Input `project-path`. (Reproduces bifrost
   DR-13.)
2. [VERIFY] `actionlint`; canary publishes+runs bifrost's AOT sample successfully.

**Dependencies:** None. **Parallelizable:** Yes.

### Task 9: `benchmark-smoke` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] `actions/benchmark-smoke/action.yml`: `dotnet run --project <bench> -c Release --
   --job Dry --filter '*'`. Inputs `benchmark-project`, `filter`.
2. [VERIFY] `actionlint`; canary runs bifrost's benchmark dry run.

**Dependencies:** None. **Parallelizable:** Yes.

### Task 10: Smoke-actions canary + no-op-by-omission check
**Phase:** VERIFY
1. [VERIFY] Canary invokes both actions (succeed); confirm a caller omitting them is
   unaffected (opt-in).

**Dependencies:** Tasks 8, 9. **Parallelizable:** No.

---

## Group E — bifrost reference migration (DR-5, repo: `lvlup-sw/bifrost`)

**Hard dependency:** must run AFTER task-13 (org tagged), pinning to that SHA/tag.

### Task 11: Migrate bifrost as the reference consumer — rewrite `ci.yml`, delete the fork (DR-5)
**Phase:** GREEN
1. [GREEN] Rewrite `.github/workflows/ci.yml`: call org `build-and-test.yml` (or compose
   `dotnet-build-test`); add jobs/steps for `aot-smoke` + `benchmark-smoke`; call
   `coverage-gate` with `gate-mode: per-assembly, metrics: line+branch`. **Delete bifrost's
   `scripts/ci/coverage-gate.sh` + `coverage-gate.test.sh` + `testdata/`** (now upstream).
   Pin every org `uses:` to a 40-char SHA (consistent with #19).

**Dependencies:** Task 13. **Parallelizable:** No.

### Task 12: Migrate bifrost as the reference consumer — verify CI green end-to-end (DR-5)
**Phase:** VERIFY
1. [VERIFY] On a bifrost PR: build + tests + AOT smoke + benchmark smoke + per-assembly+
   branch gate (all 9 assemblies ≥80%) all green; no remaining local gate fork.

**Dependencies:** Task 11. **Parallelizable:** No.

---

## Group F — versioning, backward-compat, rollback (DR-6, repo: `lvlup-sw/.github`)

### Task 13: Tag a release + consumer pinning/migration guide
**Phase:** GREEN
1. [GREEN] Tag `lvlup-sw/.github` `v1` at the merged composite-layer commit; write a
   migration guide (how to pin `@<sha>`/`@v1`, opt into `gate-mode: per-assembly`). Add/note
   Dependabot for action pins.

**Dependencies:** Tasks 4, 7, 10. **Parallelizable:** No.

### Task 14: Backward-compat parity guard for existing consumers
**Phase:** TEST → VERIFY
1. [TEST] A CI check (or documented manual gate) demonstrating strategos/basileus get
   identical gate behavior under the rebuilt default workflow before any version bump
   reaches them.
2. [VERIFY] Rollback path exercised once: pin a consumer to the previous SHA → prior
   behavior restored.

**Dependencies:** Tasks 3, 6. **Parallelizable:** No.

### Task 15: Follow-up issue — remaining migrations
**Phase:** GREEN
1. [GREEN] File an issue tracking: valkyrie `coverage-gate.sh` fork convergence + migrating
   the hand-rolled C# repos (authscript, ares-elite-platform, Ecs.CSharp.Benchmark) to the
   composable layer, repo-by-repo.

**Dependencies:** None. **Parallelizable:** Yes.

---

## Sequencing

```
.github repo:  [T1] → Group B (T2→T3→T4) ┐
               Group C (T5→T6→T7) ────────┼─→ [T13 tag] ──→ bifrost: [T11]→[T12]
               Group D (T8,T9→T10) ───────┘        ↑
               [T14 parity/rollback] ←── T3,T6 ─────┘
               [T15 follow-up] (anytime)
```

- **Org-repo parallel groups:** {T1→B}, {C}, {D}, {T15}. Barrier: **T13 tag** gates the
  bifrost migration.
- **Cross-repo barrier:** T11/T12 (bifrost) only after T13 (org tagged).

## Risks

- **Cross-repo execution** (above) — the dominant operational risk; resolve the execution
  model at plan-review before any delegation.
- **Silent default-behavior shift** for existing consumers — guarded by T1's parity lock +
  T14; unchanged defaults are the contract.
- **Canary fidelity** — the org canary must exercise a real .NET project (bifrost) to catch
  MTP/coverage regressions the fixtures can't.

## Open design questions — resolutions (confirm at plan-review)

1. **Execution model** for the cross-repo work (clone `.github` + separate run, vs. manual
   org PR + exarchos for bifrost only). *(No default — needs your call.)*
2. **Pin style** `@v1` vs `@sha`. *(Default: `@sha`, Dependabot-managed.)*
3. **Scope of workflow rebuilds** — only build-test + coverage-gate now (update-baseline /
   format-check follow the pattern later). *(Default: in-scope two only.)*
