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

## Tag move: before a maintainer moves `v1`

Moving the `v1` tag changes the resolved ref for every `@v1` consumer with no
PR, no approval, and no CI on their side. The consumer-bump procedure above does
not cover this direction. Run this **before** `git tag -f v1` / a GitHub release
that retargets `v1`.

### Who to parity-check, and in what order

A tag move that only adds an opt-in input (`enabled`, `exclude-sources`) still
needs a default-input check: the load-bearing promise is that defaults stay
byte-identical. Stop at the first consumer whose coverage verdict or PR comment
differs; do not move the tag.

1. **This repo's canaries.** `canary-coverage-gate.yml` `default-parity` and
   `canary-enabled-input.yml` on `main` after the release commit. If those are
   red, the building blocks are not safe to point `v1` at.
2. **strategos** — reference consumer of the reusable workflows
   (`build-and-test.yml` / `coverage-gate.yml` at default-ish inputs, required
   two-part checks).
3. **basileus** — second .NET reusable consumer; historically inherited the
   unrunnable `self-hosted` default. Confirm `runner:` is still passed.
4. **bifrost** — org `canary-build-test` fixture and a composite-action
   consumer (`dotnet-build-test`, `coverage-gate.yml`). A behavior change here
   also breaks this repo's canary.
5. **The rest, in any order, only if 1–4 match:** charter, pythia, brokerdex,
   blockfront, hierophant. Skip DataFerry (archived). Skip exarchos and
   ares-elite-platform unless the release changes `actions/ci-lanes` — they do
   not call the coverage reusable.

### What to capture

On each consumer, open a no-op PR against current `v1` (or wait for a live PR
that already runs coverage). Then, on a throwaway branch, temporarily pin that
consumer at the **proposed** commit (the SHA `v1` will move to) with no input
changes, and open a second PR.

Compare:

- Coverage job **verdict** (pass/fail) identical.
- Coverage **PR comment** identical line-for-line.
- Required check **names** still report. A skipped reusable inner job must keep
  its two-part name (`build-test / Build & Test`). A missing name is a release
  bug, not a consumer bug.

Gate on a zero diff. Any diff → do not move `v1`; file against this repo.

### Version tags are immutable; only the major alias moves

The `version-tags-immutable` ruleset denies `update` and `deletion` on
`refs/tags/v*.*`. A `v1.N` cut therefore cannot be force-moved or deleted once
pushed. The pattern needs a literal dot, so `v1` (and a future `v2`) stays
movable — the alias is the only thing this procedure advances.

This exists because a consumer can bind a digest to a workflow's bytes. Pin an
authority digest, an attestation, or a recorded job hash against a ref that can
move, and the digest keeps matching while the code behind the ref changes. That
is the substitution such a digest exists to prevent. `lvlup-sw/hierophant` does
exactly this, which is why it SHA-pins rather than using `@v1`.

Consequences for a maintainer:

- **Never re-cut a published `v1.N`.** A bad release is superseded by the next
  cut, not repaired in place. Roll consumers back by repinning, as below.
- The `v1` alias is unaffected and still moves through the procedure above.
- Enabling **Settings -> General -> Releases -> Immutable releases** covers
  newly published releases; the ruleset is what covers the tags already cut.

### After the move

1. Confirm `git rev-parse v1` equals the intended commit.
2. Re-run the org canaries on `main`.
3. Watch the next PR on strategos and bifrost. If either is red in a way the
   pre-move PRs were not, revert `v1` to the previous commit (a tag move is the
   rollback) and file the regression here.

### Status

The consumer-bump procedure is for a repo changing *its own* pin. The tag-move
procedure is for a maintainer changing the pin *under* every `@v1` consumer.
Use both. Do not treat a green canary in this repo as a substitute for
strategos / basileus / bifrost.
