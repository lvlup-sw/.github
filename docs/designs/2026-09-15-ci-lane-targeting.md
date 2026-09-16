# Design: CI lane targeting (`ci-lanes` action + `enabled` input)

**Driver:** `lvlup-sw/hierophant`. PR #466 changed template pins and three scripts, and it started 26 CI jobs. Most of them built and tested code the PR did not touch.
**Prior art in the org:** `exarchos` and `ares-elite-platform` each have a hand-written `changes` job on `dorny/paths-filter@v3` and a hand-written `CI Gate`.

## Problem

Org consumers run their whole CI on every PR. A docs-only PR still builds, tests, and gates coverage.

Path filters on the trigger do not solve this. A required status check that never reports blocks the PR forever. So a consumer needs its jobs to skip inside a run that always reports. Three GitHub behaviours make that easy to get wrong:

1. **A skipped inline job reports success** under its own check name. A skip condition that trusts a failed or missing planner output is therefore fail-open.
2. **A skipped job that calls a reusable workflow reports a different name.** It reports as `build-test`, not `build-test / Build & Test`. A ruleset that requires the two-part name waits forever ([community #72708](https://github.com/orgs/community/discussions/72708)).
3. **A matrix job skipped at job level never expands.** Its per-leg check names never appear ([actions/runner #952](https://github.com/actions/runner/issues/952)).

The two existing copies in the org each learned part of this the hard way. In exarchos, a renamed `changes` output let four lanes skip while `CI Gate` reported success.

## Chosen approach

### 1. The `ci-lanes` composite action

A consumer commits a TOML manifest, `.github/ci-lanes.toml`. Each lane names the paths its jobs read and the workflow files that host those jobs. The action has three modes.

- **`plan`** diffs `base...head` from a full-history checkout. It publishes one output, `lanes`, a JSON object of `"true"` or `"false"` per lane.
  - Any event that is not `pull_request` runs every lane.
  - A change to the manifest runs every lane.
  - A change to a lane's workflow file runs that lane.
  - It needs no token and makes no API call, so it does not spend the shared rate limit.
- **`verdict`** runs in a gate job over `toJSON(needs)`. Every covered job must succeed. A `skipped` result passes only if all three hold:
  - the manifest maps the job to a lane,
  - the planner succeeded, and
  - that lane is exactly `"false"`.
- **`check`** is a static contract that runs in the consumer's contract gate. It proves that:
  - every targeted job uses one of the two exact forms below;
  - a matrix job skips at job level only when a gate covers it;
  - each gate needs exactly the planner plus its covered jobs;
  - every glob still matches a tracked file, and every lane is read by some job;
  - every repository path a job names is inside its lane;
  - every recorded fixture still replays to its expected decisions.

The two forms `check` accepts are:

```yaml
if: ${{ always() && (needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).<lane> != 'false') }}
enabled: ${{ needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).<lane> != 'false' }}
```

GitHub compares loosely and coerces mismatched types to numbers. So `!= 'false'` is true for a missing key, and a typo in a lane name runs the job.

### 2. The `enabled` input on the reusable workflows

`build-and-test.yml`, `coverage-gate.yml`, `format-check.yml`, and `node-build-test.yml` gain `enabled` (boolean, default `true`). The inner job gets `if: ${{ inputs.enabled != false }}`. `dependency-review.yml` gained the same input afterwards, for the same reason: it is a PR-time gate a docs-only change cannot affect. Two are excluded. `update-baseline.yml` runs on pushes to the default branch, where every lane runs. `codeql.yml` names its inner job `Analyze (${{ inputs.languages }})`, and GitHub does not evaluate the name of a job it never starts, so a skipped run reports a different check context than a real one — `enabled:` there would break the required check instead of preserving it. Giving codeql the input requires a static inner job name, which changes the required check name in every consumer ruleset and is therefore its own coordinated change.

- The caller always runs, so the check keeps its two-part name while the inner job skips. That removes behaviour 2 for the org's own reusables.
- The default keeps every existing consumer byte-identical.
- The condition is `!= false`, not a bare `inputs.enabled`. Only the literal boolean `false` skips.

### 3. Language: Python, standard library at runtime

- **Speed.** Every targeted job waits for the planner, so start-up time matters. C# needs an SDK install and a compile, or a separate release channel for a prebuilt tool.
- **No third-party runtime dependencies.** Python 3.11+ ships `tomllib`, and `git` runs as a subprocess.
- **Only `check` needs PyYAML (6.0.2),** and the action pins it.
- **The interpreter is a uv-managed CPython 3.12,** so the runner's system Python does not matter.
- **Testing.** The package ships with `mypy --strict` and a `unittest` suite. The suite covers the full verdict grid and the hostile `check` edits.

### Rejected alternatives

- **`dorny/paths-filter`.** It is an unpinned third-party action that decides which required checks run. By default it lists PR files through the REST API. It has no verdict or contract check.
- **A `CI Gate` in front of everything.** It changes every consumer's required checks. `enabled` keeps the existing names, so a gate is needed only for matrices.
- **Filtering on the workflow's `paths:`.** A required check that never reports blocks the PR forever.

## Canaries (self-test)

- **`canary-ci-lanes.yml`:**
  - (a) `mypy --strict` and the unit suite.
  - (b) `plan` over the PR's own diff through the real action wiring.
  - (c) GitHub's own evaluation of the canonical skip: exact `'false'` skips; `'true'`, a missing key, and a planner that did not succeed all run.
  - (d) `verdict` passes a licensed skip and fails an unlicensed skip, a relevant skip, a failure, and unreadable input.
  - (e) `check` accepts the clean consumer fixture and refuses a broken one.
- **`canary-enabled-input.yml`** calls all four reusables with `enabled: false`. It then reads the run's job list and asserts two things. First, each skipped inner job reports under `<caller> / <job name>`, and no single-part caller name appears. Second, every caller result is `skipped`, not `success`. The first canary run proved this: a downstream caller that needs a disabled caller is skipped at caller level and reports a single-part name. A chained caller must therefore run with `if: always()` and test the upstream result for `failure` or `cancelled` itself.

## Versioning / rollout

Merge to `main`. Then cut `v1.7` and move `v1` to the merge commit. Dependabot bumps consumers. Nothing changes for a consumer until it opts in.

## Consumer wiring (hierophant, separate PRs)

1. **Inline targeting.**
   - Add the manifest, a planner job, and the canonical skip on the inline guard jobs.
   - Run `check` in `Workflow Contract`.
   - Swap the in-step selector for `ci-lanes` with `lane:`.
   - This needs no ruleset change.
2. **Pre-authorize.** Record the release-evidence authority for the `v1.7` reusable refs. Replace the six Terraform matrix contexts with one `Terraform Gate`.
3. **Adopt `v1.7`.** Move the reusable callers to `v1.7` with `enabled:`, and add the Terraform matrix skip.
4. **Retire** the `v1.6` authority records.

## Follow-ups

- Migrate `exarchos` and `ares-elite-platform` off `dorny/paths-filter` and their hand-written gates.
- Offer `ci-lanes` to `basileus`, `strategos`, and the other `build-and-test.yml` consumers.
