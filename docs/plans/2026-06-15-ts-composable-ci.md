# Implementation Plan: TypeScript Composable CI Layer

**Design:** `docs/designs/2026-06-15-ts-composable-ci.md`
**Discovery:** `docs/research/2026-06-15-ts-composable-ci.md`
**Feature ID:** `ts-composable-ci-impl`
**Date:** 2026-06-15

## ⚠️ Cross-repo execution note

Tasks 1–10 land in **`lvlup-sw/.github`** (this repo, alongside `actions/`).
Tasks 11–12 (the exarchos reference migration, DR-T5) land in
**`lvlup-sw/exarchos`** and are **deferred + gated on the release tag** — exactly
as the C# layer deferred the bifrost migration. They are tracked in
lvlup-sw/exarchos#1539; do not run them in this repo's worktrees.

## TDD shape

CI infra (YAML + one zero-dep JS merge helper + bash). "Failing test first" maps
to: a **genuine unit test** for the cobertura merge helper (RED→GREEN, `node:test`);
a **cross-language Cobertura fixture + harness case** on the existing
`scripts/ci/coverage-gate.test.sh` (RED-guards any C#-specific assumption in the
shared gate); and **`actionlint` + a canary workflow** for the new actions/workflow
(`[VERIFY]`). The exarchos migration is green-end-to-end-CI (`[VERIFY]`).

## Traceability

| DR | Requirement | Tasks | Repo |
|----|-------------|-------|------|
| DR-T2 | Reuse coverage-gate for TS + cross-language fixture | 1, 2 | .github |
| DR-T1 | `node-build-test` action (+ merge helper) | 3, 4, 5 | .github |
| DR-T3 | `node-benchmark-smoke` action | 6 | .github |
| DR-T4 | Preset workflow + canary + guide + versioning | 7, 8, 9, 10 | .github |
| DR-T5 | Migrate exarchos (reference consumer) | 11, 12 | exarchos |

---

## Group A — cross-language gate fixture (DR-T2)

### Task 1: Cross-language Cobertura fixture + harness case
**Phase:** RED → VERIFY
1. [RED] Add a **vitest/istanbul-produced** Cobertura fixture (directory-style
   `<package name="src/...">`, root `line-rate`/`branch-rate`) to
   `scripts/ci/testdata/ts-vitest.cobertura.xml`. Add a case to
   `scripts/ci/coverage-gate.test.sh` asserting the gate reads it: aggregate
   (default) verdict + per-`<package>` rows in `pr-comment.md`. Against today's
   gate this should pass — it **RED-guards** any future C#-specific assumption.
2. [VERIFY] harness green including the new case.

**Dependencies:** None. **Parallelizable:** Yes. **testingStrategy:** script-fixture.

### Task 2: Confirm gate language-agnosticism under test
**Phase:** VERIFY
1. [VERIFY] `bash scripts/ci/coverage-gate.test.sh` all cases pass (incl. Task 1);
   no edit to `coverage-gate.sh`'s default path. Locks the discovery F1 claim.

**Dependencies:** Task 1. **Parallelizable:** No.

---

## Group B — `node-build-test` action + merge helper (DR-T1)

### Task 3: Cobertura merge helper — unit test
**Phase:** RED
1. [RED] Write `scripts/ci/merge-cobertura.test.mjs` (`node:test`): merging two
   Cobertura files yields one whose `lines-valid/covered` + `branches-valid/covered`
   are the summed totals and `line-rate`/`branch-rate` are recomputed from them;
   per-`<package>` rows are unioned. Expected failure: helper does not exist.
   - File: `scripts/ci/merge-cobertura.test.mjs`

**Dependencies:** None. **Parallelizable:** Yes.

### Task 4: Cobertura merge helper — implement
**Phase:** GREEN → REFACTOR
1. [GREEN] `scripts/ci/merge-cobertura.mjs` — **zero-dependency** pure-JS: parse N
   Cobertura files, sum the count attributes, recompute rates, union packages,
   emit one merged `Cobertura.xml`. (Keeps `.github` dep-free; used only for the
   multi-root case.)
2. [REFACTOR] tidy; `node --test scripts/ci/merge-cobertura.test.mjs` green.

**Dependencies:** Task 3. **Parallelizable:** No.

### Task 5: `node-build-test` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] `actions/node-build-test/action.yml` (composite): detect PM from
   lockfile (`package-lock.json`→npm / `pnpm-lock.yaml`→pnpm / `bun.lock(b)`→bun)
   → `setup-node` (+ pnpm/bun setup) → frozen install → `tsc --noEmit` (when
   `typecheck`) → **opt-in** lint (only if `lint-command` set) →
   `vitest run --coverage --coverage.reporter=cobertura --coverage.reporter=text-summary`
   → single merged Cobertura (vitest-native single run; else `merge-cobertura.mjs`)
   → upload `coverage-reports` → `tests-passed` output. Untrusted inputs via `env:`.
   Inputs include `coverage-provider` (default `v8`; `istanbul` = the instrumented
   TSX/JSX fallback, per design Open-Q3).
2. [VERIFY] `actionlint` clean; PM-detect logic covered in the canary (Task 8).

**Dependencies:** Task 4. **Parallelizable:** No.

---

## Group C — opt-in smoke (DR-T3)

### Task 6: `node-benchmark-smoke` composite action
**Phase:** GREEN → VERIFY
1. [GREEN] `actions/node-benchmark-smoke/action.yml`: `vitest bench --run` (quick).
   Inputs `working-directory`, `bench-command` (default `vitest bench --run`),
   `package-manager` (auto). Opt-in / no-op by omission.
2. [VERIFY] `actionlint`; exercised in the canary.

**Dependencies:** None. **Parallelizable:** Yes.

---

## Group D — preset workflow, canary, guide, release (DR-T4)

### Task 7: `node-build-test.yml` preset workflow
**Phase:** GREEN → VERIFY
1. [GREEN] `.github/workflows/node-build-test.yml` — thin preset over
   `node-build-test`, mirroring `build-and-test.yml`'s signature shape
   (`working-directory`, `node-version`, `package-manager`, `lint-command`,
   `runner`); `tests-passed` output. Internal action ref SHA-pinned (T13 pattern).
2. [VERIFY] `actionlint`; signature sane.

**Dependencies:** Task 5. **Parallelizable:** No.

### Task 8: Canary workflow
**Phase:** VERIFY
1. [VERIFY] `.github/workflows/canary-node-ci.yml` (PRs touching `actions/node-*`
   / the preset): run `node-build-test` against a tiny fixture TS project (committed
   under a test path) → merged Cobertura; `coverage-gate` **action** PASSES at
   default and FAILS a seeded sub-threshold; `node-benchmark-smoke` runs; a caller
   omitting the smokes is unaffected. Include a **PM auto-detect matrix** leg
   (npm/pnpm/bun lockfile fixtures) asserting each resolves the right installer.
   `actionlint` gates all YAML.

**Dependencies:** Tasks 5, 6, 7, 1. **Parallelizable:** No. **testingStrategy:** canary-integration.

### Task 9: TS consumer guide + granularity note
**Phase:** GREEN
1. [GREEN] Extend `docs/guides/org-ci-consumer-guide.md` (TS section): `node-build-test`
   + `node-benchmark-smoke` usage, consuming `coverage-gate` as an **action** on the
   pre-merged report (no .NET ReportGenerator), pinning/Dependabot, and the
   **per-directory `<package>`** granularity note (per-assembly mode gates
   per-directory for TS; documented, gate script unchanged).

**Dependencies:** None. **Parallelizable:** Yes.

### Task 10: Release v1.1 (additive)
**Phase:** GREEN
1. [GREEN] After Tasks 1–9 merge: tag **`v1.1`** (additive — C# `v1` untouched) and
   publish release notes covering the new `node-*` actions + preset. Dependabot
   already globs `/actions/*`, so the new actions need no config change.

**Dependencies:** Tasks 2, 5, 6, 7, 8, 9. **Parallelizable:** No.

---

## Group E — exarchos reference migration (DR-T5, repo: `lvlup-sw/exarchos`)

**Hard dependency:** AFTER Task 10 (org tagged `v1.1`). Tracked in exarchos#1539.

### Task 11: Migrate exarchos CI onto the layer
**Phase:** GREEN
1. [GREEN] Rewrite exarchos CI: call `node-build-test` (auto-detect npm) +
   `coverage-gate` action (gate coverage — currently ungated) + `node-benchmark-smoke`
   (replacing the bespoke `vitest bench` gate). Handle the two package roots (root +
   `servers/exarchos-mcp`) via the merge helper or two invocations. Pin org refs `@v1.1`/`@<sha>`.

**Dependencies:** Task 10. **Parallelizable:** No.

### Task 12: Verify exarchos CI green end-to-end
**Phase:** VERIFY
1. [VERIFY] On an exarchos PR: install/typecheck/test + **gated coverage** +
   benchmark smoke all green; no hand-rolled coverage logic remaining; org refs pinned.

**Dependencies:** Task 11. **Parallelizable:** No.

---

## Sequencing

```
.github:  [T1→T2] ─────────────────────────┐
          [T3→T4→T5→T7] ───────────────────┼─→ [T8 canary] → [T10 tag v1.1] ─→ exarchos: [T11→T12]
          [T6] ───────────────────────────┘                      ↑
          [T9 guide] (anytime) ───────────────────────────────────┘
```

- **Org-repo parallel groups:** {A: T1→T2}, {B: T3→T4→T5→T7}, {C: T6}, {T9}. Barrier: **T8 canary** then **T10 tag**.
- **Cross-repo barrier:** T11/T12 (exarchos) only after T10 (org tagged `v1.1`).

## Risks

- **vitest v8 Cobertura accuracy on TSX/JSX** — expose a `coverage-provider` input;
  istanbul is the instrumented fallback.
- **Multi-root merge correctness** — the merge helper is unit-tested (T3/T4) and
  exercised on exarchos's two-root layout (T11).
- **Gate language-agnosticism regressing** — the cross-language fixture (T1) is the
  standing guard; never add C#-specific assumptions to `coverage-gate.sh`.

## Open design questions — resolutions

1. **Release versioning:** additive **`v1.1`** (C# `v1` untouched). *(Confirmed default.)*
2. **`per-package` gate alias:** document-only per-directory semantics; do not touch
   the shared script this round. *(Confirmed default.)*
3. **Coverage provider default:** v8 (AST remapping) with a selectable
   `coverage-provider` input for the TSX fallback. *(Confirmed default.)*
