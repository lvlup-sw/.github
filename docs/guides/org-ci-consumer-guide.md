# Org CI: Consumer Pinning & Migration Guide

**Applies to:** `lvlup-sw/.github` composite CI layer, `v1` and later.
**Design / plan:** `docs/designs/2026-06-15-org-ci-rearchitecture.md`,
`docs/plans/2026-06-15-org-ci-rearchitecture.md`.

The org now ships CI as **composable building blocks**: composite actions, plus
thin preset reusable workflows built on top of them (the table below is the
catalog). This guide is for repos that consume them — how to pin a version, which
building block to use, and how to opt into the stricter coverage gate.

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
| `deploy.yml` (reusable workflow) | `.github/workflows/deploy.yml` | Turnkey: a secretless, environment-gated Terraform `plan`/`apply`/`destroy` as its own job. |
| `terraform-deploy` (composite action) | `actions/terraform-deploy` | Compose Terraform `plan`/`apply`/`destroy` as steps **inside your own job** — e.g. apply → assert → destroy on one runner. |
| `ci-lanes` (composite action, `v1.7`+) | `actions/ci-lanes` | Start only the jobs a PR can affect, without letting a skip hide a failure. See [Targeting jobs to changed paths](#targeting-jobs-to-changed-paths-v17). |

**Workflow vs action:** use a **reusable workflow** when the org-standard job is
all you need (one `uses:` line). Use the **composite actions** when you need to
add your own steps *around* the standard ones — the GitHub reusable-workflow
model cannot accept caller-injected steps, which is the whole reason the actions
exist. Composite actions also can't declare `matrix` / `services` / job-level
`permissions`; those stay in your caller workflow.

## Targeting jobs to changed paths (`v1.7`+)

Design: `docs/designs/2026-09-15-ci-lane-targeting.md`.

A PR that changes only docs or config does not need to build and test
everything. The `ci-lanes` action lets a job skip when the PR does not touch the
paths the job reads. It is built so that a skip can never hide a failure.

**1. Commit a manifest** at `.github/ci-lanes.toml`. A lane names the paths its
jobs read and the workflow files that host those jobs:

```toml
schema_version = 1

[lanes.build_test]
workflows = ["ci.yml"]
paths = ["src/**", "tests/**", "*.slnx", "Directory.*.props", "global.json"]

[[fixtures]]                 # `check` replays these against the pinned engine
name = "docs-only change"
files = ["README.md"]
expect = { build_test = false }
```

**2. Add a planner job** that needs full history (no file contents):

```yaml
  plan:
    runs-on: ubuntu-latest
    outputs:
      lanes: ${{ steps.plan.outputs.lanes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          filter: blob:none
      - id: plan
        uses: lvlup-sw/.github/actions/ci-lanes@v1
```

**3. Target each job.** Use exactly one of these two forms. `check` refuses any
other form.

```yaml
  # An inline job: a skipped job reports success under its own check name.
  integration-tests:
    needs: plan
    if: ${{ always() && (needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).build_test != 'false') }}

  # A reusable-workflow caller: pass the decision down as `enabled`.
  build-test:
    needs: plan
    if: always()
    uses: lvlup-sw/.github/.github/workflows/build-and-test.yml@v1
    with:
      runner: ubuntu-latest
      enabled: ${{ needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).build_test != 'false' }}
```

Why these exact forms:

- **Only the exact string `'false'` skips.** If the planner fails, or reports no
  value for the lane (for example, a typo), the job runs.
- **Never put the skip on the caller of a reusable workflow.** A skipped caller
  reports its check as `build-test`, not `build-test / Build & Test`. A required
  check with the two-part name then waits forever. `enabled: false` skips the
  inner job and keeps the two-part name.
- **Chain reusable callers with `if: always()`.** A caller whose inner job
  skipped has result `skipped`, not `success`. A caller that needs it (for
  example `coverage-gate` after `build-test`) is otherwise skipped at caller
  level and reports a single-part name. Test the upstream result yourself:
  `if: ${{ always() && needs.build-test.result != 'failure' && needs.build-test.result != 'cancelled' }}`.
- **Never skip a matrix job at job level unless a gate covers it.** A skipped
  matrix never creates its per-leg checks. Declare a `[gates.<job>]` in the
  manifest, make the gate the required check, and run
  `ci-lanes` with `mode: verdict` in it.
- **Pushes and every other non-PR event run every lane.** The push to your
  default branch is the backstop for a lane that misses a path.

**4. Run `check`** in a job that runs on every PR (for example, your workflow
contract job): `uses: lvlup-sw/.github/actions/ci-lanes@v1` with
`mode: check`. It proves, among other things, that every job uses one of the forms above,
that every glob still matches a tracked file, and that every repository path a
job names is inside its lane.

**Keep security scans unconditional.** Secret and data-leak scans must not need
the planner: a leak can land in any path.

## Pinning

Pin every org `uses:` to **`@v1`**. That is the paved road: the template emits
it, `template-smoke.sh` asserts it, and every active consumer tracks the same
line. A moving tag has no review gate on the consumer side — before a maintainer
moves `v1`, follow the tag-move procedure in
`docs/runbooks/org-ci-parity-and-rollback.md`.

**`@<40-char SHA>` is an opt-out**, not a second paved road. Use it only when a
repo explicitly chooses the stronger supply-chain guarantee (a tag can be moved;
a SHA cannot). Do not mix SHA and `@v1` in the same repository.

**Never pin `@main`** — it floats and defeats reproducibility.

**Always pass `runner:`** on `build-and-test.yml` and `coverage-gate.yml`. The
reusable default is `self-hosted`, which matches no runner registered in this
org. Omitting it queues a required check forever. Pass `ubuntu-latest` unless
the repo has a documented, registered runner label of its own. Do not rely on
the default changing in a later release — a tag move must not silently retarget
runners.

```yaml
# Reusable workflow — pin the workflow file:
jobs:
  test:
    uses: lvlup-sw/.github/.github/workflows/build-and-test.yml@v1
    with:
      runner: ubuntu-latest
      solution-path: MyProject.slnx
      test-project-patterns: |
        **/tests/**/*.Tests.csproj

  coverage:
    needs: test
    uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@v1
    with:
      runner: ubuntu-latest
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

**Optional — keep generated code out of coverage** (`build-and-test.yml` and the
`dotnet-build-test` action): set `exclude-generated: true` to pass a default
Microsoft code-coverage settings file during collection that drops elements
carrying `[GeneratedCodeAttribute]` and sources matching `.g.cs` / `.Designer.cs`.
Opt-in; the default (`false`) leaves collection unchanged. Use it when a
source generator emits code that isn't stamped `[ExcludeFromCodeCoverage]` and
would otherwise dilute the coverage denominator.

**Optional — target the coverage denominator at hand-written logic**
(`exclude-sources`): newline-separated ECMAScript regexes matched against source
file *paths*. Any file that matches is dropped from collection. It composes with
`exclude-generated`, which supplies the generated-code rules.

```yaml
with:
  exclude-generated: true
  exclude-sources: |
    .*[/\\]Program\.cs$
```

Reach for this when the gate is measuring code nobody writes. `coverage-filters`
cannot do it — that is ReportGenerator's `-assemblyfilters`, so it only works at
assembly granularity. A source-level `[ExcludeFromCodeCoverage]` cannot do it
either when the generator emits C# `file`-scoped types, because those are not
`partial` and cannot be referenced from another file.

Two denominator entries this targets:

| Entry | Why it dilutes | Rule |
|---|---|---|
| Host bootstrap (`Program.cs` top-level statements) | DI, health, and OpenAPI wiring, not logic | `.*[/\\]Program\.cs$` |
| A generated support class the generator does not stamp | Emitted per-assembly, unreachable by tests | `exclude-generated: true` |

Measured on a scaffolded service (`lvlup-sw/blockfront`, 7 tests): 7.48% with
neither lever, 18.72% with `exclude-generated`, 30.2% with both. The last number
is the honest one — it counts only hand-written code, and it correctly reports
that the repo's schedule services have no tests.

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

`@v1` consumers pick up a new release when the org moves the tag — there is no
Dependabot PR on their side. That is why the tag-move procedure in
`docs/runbooks/org-ci-parity-and-rollback.md` exists.

Action pins in **this org repo** are bumped by **Dependabot**
(`.github/dependabot.yml`). A consumer that opted out to a SHA pin should add a
`github-actions` Dependabot (or Renovate) entry so those pins get update PRs.
Don't run both bots against the same `uses:` refs.

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
| `assembly-thresholds` | newline list of `GLOB = LINE[/BRANCH]` | `per-assembly` only: risk-tiered floors. First matching rule wins; unmatched assemblies use `coverage-threshold`. Omit `BRANCH` to gate line only. |

```yaml
# bifrost-style strict gate: every assembly ≥ 80% line AND branch
  coverage:
    uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@v1
    with:
      runner: ubuntu-latest
      coverage-threshold: 80
      gate-mode: per-assembly
      metrics: line+branch
```

```yaml
# risk-tiered gate: hold security/boundary higher than domain logic, and
# don't chase branch % on host wiring. coverage-threshold is the fallback floor.
  coverage:
    uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@v1
    with:
      runner: ubuntu-latest
      coverage-threshold: 80
      gate-mode: per-assembly
      assembly-thresholds: |
        *Identity*            = 85/75
        *McpToken*            = 85/75
        *CodeExecutionBridge* = 85/75
        *Trading*             = 80/70
        *.Core                = 80/70
        *.Host                = 70      # line only (boot-tested elsewhere)
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

## Terraform deploy (`v1.6`+)

The org's **secretless** Terraform deploy spine: federated GitHub OIDC →
`azure/login` → `terraform init` → `plan` / `apply` / `destroy`.

**There are no Azure secrets to configure, and you must not add any.** Auth is
federated OIDC; there is no client-secret path anywhere in the chain. The OIDC
ids are *identifiers, not credentials* — pass them as repo **variables**:

```yaml
jobs:
  deploy:
    permissions:
      id-token: write        # REQUIRED — see the gotcha below
      contents: read
    uses: lvlup-sw/.github/.github/workflows/deploy.yml@v1
    with:
      working-directory: infra/stamp
      mode: apply
      environment: production        # YOUR environment owns the reviewer gate
      client-id: ${{ vars.AZURE_CLIENT_ID }}
      tenant-id: ${{ vars.AZURE_TENANT_ID }}
      subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

> **Gotcha — a missing `id-token: write` fails at workflow STARTUP.** GitHub
> refuses to let a called workflow hold more permission than its caller, and
> checks it *before* running anything. If your calling job omits
> `id-token: write`, the run is marked `startup_failure` with **no jobs, no
> logs, and no step annotation** — it looks like the workflow file is broken.
> The real message, where it surfaces, is *"the workflow is requesting
> 'id-token: write', but is only allowed 'id-token: none'"*. The default
> `GITHUB_TOKEN` set has no `id-token`, so this bites every first-time caller.
> Grant it on the **calling job**.

**Workflow or action?** They are not interchangeable here:

- **`deploy.yml` (workflow)** — the deploy is its own gateable job. One `uses:`.
- **`terraform-deploy` (action)** — you need apply/destroy as **steps inside your
  own job**: an ephemeral E2E harness whose Terraform state is job-local
  (`-backend=false`) must keep every mode on one runner, with assertions
  interleaved between apply and destroy. A `workflow_call` reusable cannot run as
  steps inside your job. Both paths execute the same spine.

```yaml
# Action — apply → assert → destroy on a single runner, state never leaves it.
steps:
  - uses: actions/checkout@v4
  - uses: lvlup-sw/.github/actions/terraform-deploy@v1
    id: stamp
    with:
      working-directory: infra/stamp
      mode: apply
      backend-args: '-backend=false'
      tf-vars: '{"location":"eastus","replicas":2}'
      client-id: ${{ vars.AZURE_CLIENT_ID }}
      tenant-id: ${{ vars.AZURE_TENANT_ID }}
      subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
  - run: ./scripts/assert-stamp.sh
    env:
      STAMP: ${{ steps.stamp.outputs.terraform-outputs }}
  - if: always()          # destroy even when the assertions fail
    uses: lvlup-sw/.github/actions/terraform-deploy@v1
    with:
      working-directory: infra/stamp
      mode: destroy
      backend-args: '-backend=false'
      client-id: ${{ vars.AZURE_CLIENT_ID }}
      tenant-id: ${{ vars.AZURE_TENANT_ID }}
      subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

Notes:

- **`terraform-outputs` is filtered to NON-SENSITIVE values.** Every entry whose
  `.sensitive == true` is dropped before it leaves the action. GitHub does **not**
  mask values crossing a job/workflow output boundary, so anything you expose
  from a `sensitive` output would be readable org-wide. Mark secrets
  `sensitive = true` in your root module and read them from Key Vault instead.
- **You own your environment's protection rules.** A reusable workflow cannot
  impose a gate on its callers: `deploy.yml` applies whatever `environment:` you
  name, and naming none means **no gate**. Put required reviewers on the
  environment in *your* repo.
- **`tf-vars`** is a JSON object expanded to `TF_VAR_*`. Strings pass raw; every
  other type (number, bool, list, object) passes as compact JSON.
- **`backend-args`** goes to `terraform init` — `-backend-config=...` for a
  remote backend, or `-backend=false` for job-local state.
- `skip-login` exists only for auth-free fixture runs (the org canary). Leave it
  `false` for every real deployment.

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
  actions including the per-assembly + branch gate, and passes the
  `dotnet-build-test` `test-filter` input (`v1.2`+) an MTP `--treenode-filter` to
  exclude its `[Category=Stress]` proofs from the per-PR run (those run in a
  separate gated job). `test-filter` is optional and empty by default, so it
  changes nothing for other consumers.

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
