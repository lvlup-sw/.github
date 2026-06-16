# Discovery: TypeScript composable CI layer (parity with the C# v1 layer)

**Feature ID:** `ts-composable-ci`
**Date:** 2026-06-15
**Status:** discovery (research) — feeds a follow-on `/exarchos:ideate` design
**Tracking:** lvlup-sw/.github#12 · first consumer: lvlup-sw/exarchos#1539

## Question

The org just shipped a **C#** composable CI layer at `v1` (composite actions
`dotnet-build-test`, `coverage-gate`, `aot-smoke`, `benchmark-smoke` + thin preset
reusable workflows, SHA-pinned, Dependabot-managed). TS/JS repos (exarchos, and
future ones) still hand-roll CI — the same drift that motivated the C# layer.
What does a **TypeScript** layer at functional parity look like, and how much new
surface does it actually need?

## Parity target (the C# layer, recap)

- `dotnet-build-test` → restore/build/test with coverage → upload `coverage-reports` (Cobertura).
- `coverage-gate` → run the shared `scripts/ci/coverage-gate.sh` on a Cobertura file; post PR comment. Modes: aggregate (default) / per-project / per-assembly; metric line (default) / line+branch.
- `aot-smoke`, `benchmark-smoke` → opt-in extras.
- All consumed by SHA/`@v1` pin; composite-action model lets callers interleave their own steps.

## Findings

### F1 — The coverage gate is already language-agnostic. Reuse it as-is.

`scripts/ci/coverage-gate.sh` parses **generic Cobertura** only — `line-rate` /
`branch-rate` on the root `<coverage>` and on each `<package name=…>` — with **no
.NET-specific elements** (no assembly/namespace/culture). Fixtures already use
generic package names. The `coverage-gate` composite action sparse-checks-out the
script and runs it on whatever `Cobertura.xml` it's handed.

> Consequence: a TS repo does **not** need a parallel gate. It calls the **same**
> `coverage-gate` action (`@v1`, `shared-ref: v1`) on a Cobertura file produced by
> its TS toolchain. One gate script, one PR-comment format, across both languages.

### F2 — Vitest emits compatible Cobertura.

Vitest coverage (`coverage.reporter`) includes `cobertura` via `istanbul-reports`,
under both the `v8` and `istanbul` providers. Since v3.2.0 the V8 provider uses
AST-based remapping, producing Istanbul-identical reports — so we keep V8's speed
and get accurate, gate-readable Cobertura. The emitted XML carries the exact
`line-rate`/`branch-rate`/`<package>` attributes F1's gate reads.

*Nuance:* istanbul's Cobertura uses the source **directory** as the `<package>`
name (C# uses the assembly). So `gate-mode: per-assembly` gates **per-directory**
for TS — same mechanism, different unit. Worth a docs note / `per-package` alias
at design time, not a blocker.

### F3 — exarchos's current TS CI (the gap, concretely)

npm · Node 24 · **vitest** with the **v8** coverage provider (reporters `text`,
`json`, `html` — **no Cobertura, no threshold gate**) · `tsc --noEmit` typecheck ·
**no linter** · benchmark-gate (`vitest bench`) and eval-gate exist but are
`continue-on-error` (non-blocking) · a weekly fresh-install smoke. So: a real test
+ typecheck spine, but no coverage gate and nothing shared/composable.

## Proposed shape (minimal surface for parity)

| C# block | TS counterpart | New? |
|---|---|---|
| `dotnet-build-test` | **`node-build-test`** — install (npm/pnpm/bun, parameterized) → `tsc --noEmit` → optional lint → `vitest run --coverage --coverage.reporter=cobertura` → upload `coverage-reports` | **new** |
| `coverage-gate` | **reuse unchanged** (F1) | no |
| `benchmark-smoke` | **`node-benchmark-smoke`** — `vitest bench` (exarchos already does this) | new (opt-in) |
| `aot-smoke` | no direct analog (TS has no AOT). Optional **`install-smoke`** — `npm pack` → fresh install → CLI runs (exarchos's fresh-install-smoke, upstreamed) | optional |
| `build-and-test.yml` / `coverage-gate.yml` | **`node-build-test.yml`** + reuse `coverage-gate.yml` | one new workflow |

Net new surface: **one required action** (`node-build-test`) + **one opt-in**
(`node-benchmark-smoke`) + one preset workflow. The gate, the PR-comment, the
pinning + Dependabot conventions, and the shared `scripts/ci` all carry over.

## Open-question resolutions

- **TypeSpec?** Not applicable — it's an API-definition language, not CI tooling.
  TS coverage = vitest + istanbul-reports `cobertura`.
- **Share `scripts/ci` cross-language?** Already cross-language (bash + generic
  Cobertura). Keep it as the single source of truth for both C# and TS.
- **Package managers / lint.** Parameterize the package manager (npm/pnpm/bun)
  like `dotnet-version`; make lint opt-in (eslint/biome) since exarchos has none.
- **Monorepo coverage** (exarchos has root + `servers/exarchos-mcp` vitest
  projects): merge the per-project Cobertura outputs, or point the gate's
  `per-project` mode at a directory of `*.cobertura.xml`. Validate at design time.

## Risks to carry into design

- V8-provider Cobertura accuracy on TSX/JSX edge cases — istanbul provider is the
  fallback (slower, instrumented).
- Per-directory vs intended per-unit gating granularity (F2 nuance).
- Monorepo report merging (no ReportGenerator equivalent assumed; use istanbul
  merge or per-project mode).

## Recommendation / next step

Parity is achievable with **one new action plus reuse** — not a parallel stack.
Escalate to **`/exarchos:ideate ts-composable-ci`** to design `node-build-test`
(inputs, package-manager matrix, lint opt-in, monorepo coverage merge) against
this report, then plan/implement in `lvlup-sw/.github` alongside `actions/`.
exarchos#1539 unblocks on the first release that includes it.
