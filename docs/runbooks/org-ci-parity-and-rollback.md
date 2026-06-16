# Runbook — Org CI parity guard & rollback

The safe-bump and revert procedure for consumers of the composable CI layer
(`build-and-test.yml` / `coverage-gate.yml` and the actions under `actions/`).
Satisfies **DR-6 / T14**: prove an existing consumer's gate behavior is unchanged
*before* a version bump reaches it, and keep a tested one-step revert.

Consumer guide: `docs/guides/org-ci-consumer-guide.md`.
Design: `docs/designs/2026-06-15-org-ci-rearchitecture.md`.

## The contract being protected

Existing consumers — **strategos, basileus, DataFerry** — ran the pre-refactor
`coverage-gate.yml` at its defaults (`gate-mode: aggregate`, `metrics: line`).
The refactor's load-bearing promise is that **default-input behavior is
byte-identical** to that old script: same pass/fail verdict, same PR comment.
A version bump must not silently shift the gate.

## What already guards parity inside this repo

These run on every PR to `lvlup-sw/.github` and gate the release itself:

1. **Byte-identical script lock** — `scripts/ci/coverage-gate.test.sh` runs the
   new `coverage-gate.sh` and the **frozen** pre-refactor copy
   (`scripts/ci/testdata/coverage-gate.baseline.sh`) over the same fixtures and
   asserts identical exit code **and** byte-identical `pr-comment.md`
   (`assert_parity`). 28/28 cases pass.
2. **Default-parity canary** — `.github/workflows/canary-coverage-gate.yml`, job
   `default-parity`: runs the `coverage-gate` action at default inputs
   (aggregate/line @ 90) against a ≥90% fixture and asserts PASS + comment. The
   companion `per-assembly-failure` job proves the opt-in strict mode fails a
   seeded sub-threshold assembly.

Together these prove the *building blocks* are parity-safe. The step below is the
**consumer-level confirmation** the design calls for — run per consumer, per bump.

## Parity gate: before bumping a consumer to `@v1`

Run this on the consumer repo (example: `strategos`) before merging a bump of
its org pin from the old ref to `@v1`. It is a manual gate; gate on the diff
being **empty**.

1. On a throwaway branch, open a no-op PR (touch a README) so the consumer's
   existing CI runs against its **current** pin. Capture the coverage job's
   verdict and the posted PR-comment body. This is the baseline.
2. On a second branch off the same base, change **only** the org ref to `@v1`
   (no input changes). Open a PR; let the same coverage job run.
3. Compare:
   - **Verdict** (job pass/fail) identical.
   - **PR comment** identical line-for-line (coverage %, per-row table, verdict).
     Diff the two comment bodies; require zero diff.
4. **Identical → merge the bump. Any diff → stop**, do not bump; the defaults
   shifted and that is a release bug — file against `.github`, not the consumer.

> DataFerry is frozen; bump it only if it is reactivated, using the same gate.

## Rollback — revert a consumer to the previous pin

Every consumer is **SHA/tag pinned**, so rollback is a one-line ref change with
no code edit — instant and total.

1. Identify the previous good ref from the consumer's git history for its
   workflow file (the SHA/tag in `uses:` before the bump).
2. Repin:
   ```yaml
   # revert: was @v1
   uses: lvlup-sw/.github/.github/workflows/coverage-gate.yml@<previous-sha>
   ```
   If the consumer **composes the `coverage-gate` action directly**, also revert
   its `shared-ref` to the previous ref — otherwise the gate script stays on the
   newer version.
3. Open/merge the one-line revert PR. CI now runs the previous layer; confirm the
   coverage job reproduces the pre-bump verdict + comment (same comparison as the
   parity gate above).
4. Reopen the `.github` issue for the regression and re-pin forward only after
   the parity gate passes again.

### Status

No consumer is pinned to `@v1` yet, so there is nothing live to roll back *from*
today; this is the ready-to-run procedure. It gets its first real exercise at the
first consumer bump (bifrost via `bifrost#39`, then strategos/basileus), which is
the natural and honest place to validate it end-to-end.
