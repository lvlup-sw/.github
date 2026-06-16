# Design: TypeScript Composable CI Layer (parity with the C# v1 layer)

**Feature ID:** `ts-composable-ci`
**Date:** 2026-06-15
**Primary implementation repo:** `lvlup-sw/.github`
**Design input:** `docs/research/2026-06-15-ts-composable-ci.md` (discovery)
**Tracking:** lvlup-sw/.github#12 · first consumer: lvlup-sw/exarchos#1539

## Problem Statement

The org's composable CI layer (released `v1`: `dotnet-build-test`, `coverage-gate`,
`aot-smoke`, `benchmark-smoke` + thin preset reusable workflows) is **C#-only**.
TS/JS repos still hand-roll CI — exarchos runs vitest with the v8 provider
(json/html, **no coverage gate**), `tsc --noEmit`, no linter, and non-blocking
benchmark/eval gates. This is the same per-repo drift the C# layer was built to
end. We need a **TypeScript layer at functional parity** so TS repos consume
shared building blocks instead of forking.

Discovery established the key enabler: the `coverage-gate` action is **already
language-agnostic** (it parses generic Cobertura — `line-rate`/`branch-rate` on
`<coverage>`/`<package>`, no .NET specifics), and vitest emits compatible
Cobertura via the istanbul `cobertura` reporter (the v8 provider's AST remapping,
v3.2.0+, is Istanbul-identical). So parity needs **one new build/test action**,
not a parallel stack.

## Options Considered

### Option 1: One `node-build-test` action + reuse `coverage-gate` — CHOSEN

A single composite action produces a merged Cobertura and uploads the standard
`coverage-reports` artifact; the **existing** `coverage-gate` action gates it.
Add an opt-in `node-benchmark-smoke`. **Pros:** minimal new surface; one gate
script + one PR-comment format across both languages; single source of truth in
`scripts/ci`. **Cons:** the TS path must pre-merge coverage (the C#
`coverage-gate.yml` preset merges via ReportGenerator, a .NET tool we won't pull
into TS CI) — so TS consumes the `coverage-gate` **action** directly.

### Option 2: A TS-native gate (`coverage-gate-ts`)

Reimplement the gate in JS. **Rejected:** duplicates the gate logic, forks the
PR-comment format, and creates two sources of truth — exactly the divergence this
initiative removes. The discovery proved the bash gate is language-agnostic, so a
second gate buys nothing.

### Option 3: One mega `ci` action with a `language` input

A single action branching on `language: csharp|node`. **Rejected:** conflates two
toolchains in one file, unbounded input surface, and breaks the composite-action
ergonomic of small, single-purpose blocks.

**Rationale:** Option 1 is the only one that preserves the single-source-of-truth
gate while staying composable. It mirrors the C# layer's own winning shape.

## Chosen Approach

A `node-build-test` composite action emitting **one merged Cobertura**, the
**reused** `coverage-gate` action, an opt-in `node-benchmark-smoke`, and a thin
preset workflow — all SHA-pinned with Dependabot-managed pins, exactly like the
C# layer.

## Technical Design

**`actions/node-build-test/action.yml`** (composite):
- Inputs: `working-directory` (default `.`), `node-version` (default `lts/*`),
  `package-manager` (default `auto` — detect from lockfile:
  `package-lock.json`→npm, `pnpm-lock.yaml`→pnpm, `bun.lock(b)`→bun),
  `install-command`/`test-command` overrides (defaults derived from the detected
  PM and `vitest run --coverage`), `lint-command` (default `''` → **skipped**),
  `typecheck` (default `true` → `tsc --noEmit`), `coverage-output` (default
  `./coverage-reports/Cobertura.xml`).
- Steps: detect PM → `setup-node` (+ `setup-pnpm`/`setup-bun` as needed) →
  install (`npm ci` / `pnpm i --frozen-lockfile` / `bun install --frozen-lockfile`)
  → typecheck → **optional** lint (only if `lint-command` set) →
  `vitest run --coverage --coverage.reporter=cobertura --coverage.reporter=text-summary`
  → ensure a **single merged Cobertura** (vitest-native when projects share one
  workspace; a small pure-JS `istanbul-lib-coverage` merge when there are
  separate package roots — **no .NET ReportGenerator**) → upload `coverage-reports`
  → set `tests-passed` output. Untrusted inputs routed via `env:` (the org's
  script-injection-hardening pattern).

**`coverage-gate`** — reused unchanged. TS consumers call the **action** directly
on the pre-merged `Cobertura.xml` (skipping the C# preset's ReportGenerator step),
`shared-ref` pinned to the release.

**`actions/node-benchmark-smoke/action.yml`** (opt-in): `vitest bench` (quick/run
mode). Inputs: `working-directory`, `bench-command` (default `vitest bench --run`).

**`.github/workflows/node-build-test.yml`** — thin preset over `node-build-test`,
mirroring `build-and-test.yml`'s signature shape (working-directory, node-version,
package-manager, lint-command, runner).

## Integration Points

- **exarchos (reference consumer, #1539):** rewrite its hand-rolled CI onto
  `node-build-test` + `coverage-gate` (action), add `node-benchmark-smoke`
  (already uses `vitest bench`); pin `@<release>`.
- **`coverage-gate` / `scripts/ci`:** untouched; gains a cross-language Cobertura
  fixture in its harness (proves the language-agnostic claim under test).
- **Dependabot:** `.github/dependabot.yml` already globs `/actions/*`, so the new
  actions are auto-covered — **no config change**.
- **C# consumers (strategos/basileus/DataFerry/bifrost):** zero impact — no C#
  action, workflow, or the gate script changes.

## Blast-Radius / Migration-Impact Analysis

| Cohort | Impact | Mitigation |
|---|---|---|
| C# consumers | **None** — purely additive new actions | No edits to dotnet-* / coverage-gate / scripts/ci |
| `coverage-gate` action | Must stay language-agnostic | Add a vitest-produced Cobertura fixture to the gate harness; canary |
| exarchos | First adopter (#1539) | Migrate behind the new release tag |
| Org repo | New `actions/node-*` + preset workflow + a new release tag | Self-CI + canary; tag (e.g. `v1.1`, additive) |

**Rollback:** identical to C# — consumers are SHA/tag pinned; revert is a one-line
ref change (the existing parity/rollback runbook applies verbatim).

## Testing Strategy

- **Cross-language gate fixture (the load-bearing test):** commit a
  vitest/istanbul-produced `*.cobertura.xml` to `scripts/ci/testdata/` and assert
  `coverage-gate.sh` reads it with identical semantics (aggregate default +
  per-`<package>`). This converts discovery's F1 claim into a regression test.
- **Canary** (PR to `.github`): `node-build-test` against a small fixture TS
  project produces the merged Cobertura; `coverage-gate` passes at default and
  fails a seeded sub-threshold; `node-benchmark-smoke` runs. `actionlint` gates
  YAML.
- **Package-manager auto-detect:** matrix over npm/pnpm/bun lockfiles.
- **exarchos end-to-end:** its CI stays green on the new layer with coverage now
  gated.

## Requirements

- **DR-T1 — `node-build-test` action.** Auto-detect PM; typecheck; opt-in lint;
  vitest coverage → single merged Cobertura; upload `coverage-reports`;
  `tests-passed` output. *AC:* actionlint clean; npm/pnpm/bun detection covered;
  emits a gate-readable merged Cobertura; no .NET dependency.
- **DR-T2 — reuse `coverage-gate` for TS.** TS path consumes the action directly
  on the pre-merged report; add the cross-language Cobertura fixture + harness
  case. *AC:* gate verdict + PR comment identical-semantics on TS-produced
  Cobertura; harness green; no change to the gate script's default path.
- **DR-T3 — `node-benchmark-smoke` (opt-in).** `vitest bench`. *AC:* runs when
  invoked; no-op by omission.
- **DR-T4 — preset workflow + versioning + TS consumer guide.** Thin
  `node-build-test.yml`; pin/Dependabot parity; guide section incl. the
  per-directory `<package>` granularity note for TS (per-assembly mode gates
  per-directory; documented, gate script unchanged). *AC:* a tagged release
  includes the new actions; guide published.
- **DR-T5 — migrate exarchos (reference consumer).** Rewrite exarchos CI onto the
  layer; gated on the release tag. *AC:* exarchos CI green with coverage gated;
  no hand-rolled coverage logic remaining; org refs SHA/tag-pinned. (Lands in
  exarchos via #1539.)

## Risks

- **vitest v8 Cobertura accuracy on TSX/JSX edge cases** — istanbul provider is
  the instrumented fallback; allow the provider to be selectable.
- **Multi-root coverage merge** — keep the merge pure-JS and tiny; validate on
  exarchos's two-root layout in the canary.
- **`coverage-gate` language-agnosticism regressing** — the cross-language fixture
  test is the guard; never add C#-specific assumptions to the script.

## Open Questions

1. **Release versioning** — additive `v1.1` (C# `v1` untouched; new actions are
   purely additive) vs `v2`. *(Default: `v1.1`, additive; SHA pin remains primary.)*
2. **`per-package` gate alias** — add a TS-friendly alias for `per-assembly`, or
   only document the per-directory semantics? *(Default: document only; don't
   touch the shared script in this initiative.)*
3. **istanbul vs v8 provider default** for `node-build-test`. *(Default: v8 with
   AST remapping; expose a `coverage-provider` input for the TSX fallback.)*
