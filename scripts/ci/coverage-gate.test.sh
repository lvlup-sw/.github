#!/usr/bin/env bash
# Test harness for coverage-gate.sh
#
# Plain-bash, dependency-light. Runs the production script against fixed
# Cobertura fixtures and asserts on the EXIT CODE (the gate's verdict contract)
# AND, for the backward-compat lock, on the generated pr-comment.md byte-for-
# byte against the frozen org baseline.
#
# Run:  bash scripts/ci/coverage-gate.test.sh
#
# Each test invokes coverage-gate.sh in a throwaway tmp output dir so the
# generated pr-comment.md never pollutes the repo. Output is captured and
# only echoed on failure to keep the log readable.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/coverage-gate.sh"
DATA="$SCRIPT_DIR/testdata"
# Frozen, byte-for-byte copy of the org's PRE-upgrade coverage-gate.sh. The
# backward-compat parity cases gate the new script's DEFAULT (aggregate/line)
# path against this golden reference. Never edit it; it is the contract.
BASELINE="$DATA/coverage-gate.baseline.sh"

PASS=0
FAIL=0

# run_gate <expected-exit-code> <description> -- <gate args...>
# Asserts coverage-gate.sh exits with the expected code.
run_gate() {
    local expected="$1"; shift
    local desc="$1"; shift
    # consume the literal "--" separator
    [[ "$1" == "--" ]] && shift

    local tmp_out
    tmp_out="$(mktemp -d)"
    local log
    log="$(bash "$GATE" --output-dir "$tmp_out" "$@" 2>&1)"
    local actual=$?
    rm -rf "$tmp_out"

    if [[ "$actual" -eq "$expected" ]]; then
        echo "PASS: $desc (exit $actual)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc — expected exit $expected, got $actual"
        echo "----- captured output -----"
        echo "$log"
        echo "---------------------------"
        FAIL=$((FAIL + 1))
    fi
}

# run_gate_noxmllint — identical to run_gate but forces the script's grep/sed
# fallback extraction path. A shim dir with an executable `xmllint` stub that
# exits non-zero is prepended, so the script's xmllint calls fail and it falls
# back deterministically — even on hosts where a real xmllint is installed.
run_gate_noxmllint() {
    local expected="$1"; shift
    local desc="$1"; shift
    [[ "$1" == "--" ]] && shift

    local tmp_out shim
    tmp_out="$(mktemp -d)"
    shim="$(mktemp -d)"
    # An EXECUTABLE xmllint stub that fails (exit 127) deterministically forces
    # coverage-gate.sh onto its grep/sed fallback: `command -v` resolves even a
    # non-executable file, so the stub must be runnable and fail explicitly.
    printf '#!/usr/bin/env bash\nexit 127\n' > "$shim/xmllint"
    chmod +x "$shim/xmllint"
    local log
    log="$(PATH="$shim:$PATH" bash "$GATE" --output-dir "$tmp_out" "$@" 2>&1)"
    local actual=$?
    rm -rf "$tmp_out" "$shim"

    if [[ "$actual" -eq "$expected" ]]; then
        echo "PASS: $desc (exit $actual)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc — expected exit $expected, got $actual"
        echo "----- captured output -----"
        echo "$log"
        echo "---------------------------"
        FAIL=$((FAIL + 1))
    fi
}

# assert_parity <description> -- <default-mode gate args...>
# THE LOAD-BEARING BACKWARD-COMPAT LOCK.
#
# Runs the FROZEN org baseline and the NEW coverage-gate.sh with IDENTICAL
# default (aggregate/line) flags against the same fixture, then asserts BOTH:
#   (1) the exit code (verdict) is identical, AND
#   (2) the generated pr-comment.md is byte-identical (cmp).
# Any drift here is a silent production regression for strategos/basileus/
# DataFerry, so it must fail the harness loudly.
assert_parity() {
    local desc="$1"; shift
    [[ "$1" == "--" ]] && shift

    local old_out new_out
    old_out="$(mktemp -d)"
    new_out="$(mktemp -d)"

    local old_log new_log
    old_log="$(bash "$BASELINE" --output-dir "$old_out" "$@" 2>&1)"
    local old_exit=$?
    new_log="$(bash "$GATE" --output-dir "$new_out" "$@" 2>&1)"
    local new_exit=$?

    local ok=1
    local detail=""

    if [[ "$old_exit" -ne "$new_exit" ]]; then
        ok=0
        detail+="  verdict drift: baseline exit $old_exit vs new exit $new_exit"$'\n'
    fi

    if [[ ! -f "$old_out/pr-comment.md" ]]; then
        ok=0
        detail+="  baseline produced no pr-comment.md"$'\n'
    fi
    if [[ ! -f "$new_out/pr-comment.md" ]]; then
        ok=0
        detail+="  new script produced no pr-comment.md"$'\n'
    fi

    if [[ -f "$old_out/pr-comment.md" && -f "$new_out/pr-comment.md" ]]; then
        if ! cmp -s "$old_out/pr-comment.md" "$new_out/pr-comment.md"; then
            ok=0
            detail+="  pr-comment.md DRIFT (baseline < vs new >):"$'\n'
            detail+="$(diff "$old_out/pr-comment.md" "$new_out/pr-comment.md")"$'\n'
        fi
    fi

    if [[ "$ok" -eq 1 ]]; then
        echo "PASS: $desc (verdict + pr-comment byte-identical, exit $new_exit)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc — backward-compat parity broken"
        echo "----- parity detail -----"
        printf '%s' "$detail"
        echo "----- new script log -----"
        echo "$new_log"
        echo "--------------------------"
        FAIL=$((FAIL + 1))
    fi

    rm -rf "$old_out" "$new_out"
}

echo "=== coverage-gate.sh test harness ==="
echo

# ===========================================================================
# DR-1 — BACKWARD-COMPAT PARITY LOCK (the load-bearing requirement)
#
# A default invocation (--coverage-file <x> --threshold 80, aggregate/line) of
# the NEW script must produce a BYTE-IDENTICAL verdict (exit) AND pr-comment.md
# to the OLD org script. strategos/basileus/DataFerry depend on this exact
# output; any drift is a silent production regression. These cases RED-guard
# the replacement.
# ===========================================================================

# PASS verdict, multi-package aggregate report (brightgreen badge).
assert_parity "DR-1 parity: aggregate pass (merged multi-package) is byte-identical to org baseline" -- \
    --coverage-file "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80

# FAIL verdict, low-line single-package report (red badge), exit 1 in both.
assert_parity "DR-1 parity: aggregate fail (line below threshold) is byte-identical to org baseline" -- \
    --coverage-file "$DATA/perproject/B.cobertura.xml" --threshold 80

# Line passes / branch below threshold: org default gates LINE ONLY, so this
# must PASS (exit 0) in both — guards that the new default path did NOT pick up
# bifrost's aggregate branch gating (that is opt-in via --metrics line+branch).
assert_parity "DR-1 parity: line-pass/branch-low gates line-only (no aggregate branch gate by default)" -- \
    --coverage-file "$DATA/line85-branch70.cobertura.xml" --threshold 80

# Yellow-zone badge: coverage within +5% of threshold colors the badge yellow.
# Guards the org's get_coverage_badge_color tri-state, not just red/green.
YELLOW_FIXTURE="$(mktemp --suffix=.cobertura.xml)"
cat > "$YELLOW_FIXTURE" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.82" branch-rate="0.70" version="1.9">
  <packages>
    <package name="Yellow.Pkg" line-rate="0.82" branch-rate="0.70">
      <classes />
    </package>
  </packages>
</coverage>
XML
assert_parity "DR-1 parity: yellow-zone badge (within +5% of threshold) is byte-identical to org baseline" -- \
    --coverage-file "$YELLOW_FIXTURE" --threshold 80
rm -f "$YELLOW_FIXTURE"

# Empty-package aggregate report: the org always emits the (empty) Per-Project
# Breakdown section. Guards the new default path reproduces that structure.
NOPKG_FIXTURE="$(mktemp --suffix=.cobertura.xml)"
cat > "$NOPKG_FIXTURE" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.90" branch-rate="0.85" version="1.9">
  <packages>
  </packages>
</coverage>
XML
assert_parity "DR-1 parity: empty-package aggregate report is byte-identical to org baseline" -- \
    --coverage-file "$NOPKG_FIXTURE" --threshold 80
rm -f "$NOPKG_FIXTURE"

# Non-default threshold still matches byte-for-byte (threshold echoed in body).
assert_parity "DR-1 parity: non-default --threshold 85 is byte-identical to org baseline" -- \
    --coverage-file "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 85

# Missing coverage file: the org exits non-zero on a missing aggregate file.
run_gate 2 "DR-1: aggregate mode with a missing coverage file fails" -- \
    --coverage-file "$DATA/does-not-exist.cobertura.xml" --threshold 80

# ---------------------------------------------------------------------------
# task-15 — branch-coverage gating (OPT-IN via --metrics line+branch)
#
# Aggregate branch gating is NOT the org default (that would break parity); it
# is opt-in. With --metrics line+branch the aggregate path gates branch too.
# ---------------------------------------------------------------------------

# RED: line 85 passes, but branch 70 is below the 80 threshold → must FAIL
# under the opt-in line+branch metric.
run_gate 1 "task-15: aggregate --metrics line+branch fails on branch 0.70 < 80" -- \
    --coverage-file "$DATA/line85-branch70.cobertura.xml" --threshold 80 \
    --metrics line+branch

# GREEN: both line and branch at 0.85 → passes under line+branch.
run_gate 0 "task-15: aggregate --metrics line+branch passes on line 0.85 + branch 0.85" -- \
    --coverage-file "$DATA/line85-branch85.cobertura.xml" --threshold 80 \
    --metrics line+branch

# Backward-compat: branch-rate absent (N/A) must NOT crash; line passes → exit 0
# even under line+branch (a missing branch-rate skips the branch check).
NA_FIXTURE="$(mktemp --suffix=.cobertura.xml)"
cat > "$NA_FIXTURE" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.85" version="1.9">
  <packages>
    <package name="NoBranch.Package" line-rate="0.85">
      <classes />
    </package>
  </packages>
</coverage>
XML
run_gate 0 "task-15: missing branch-rate skips branch gate (backward compat)" -- \
    --coverage-file "$NA_FIXTURE" --threshold 80 --metrics line+branch
rm -f "$NA_FIXTURE"

# ---------------------------------------------------------------------------
# task-16 — per-project gating mode
# ---------------------------------------------------------------------------

# RED: dir has A (0.90/0.90) and B (0.60/0.55); B is below 80 → must FAIL.
run_gate 1 "task-16: --per-project fails when any project (B) is below threshold" -- \
    --per-project "$DATA/perproject" --threshold 80

# GREEN: all projects >= 80 → passes.
run_gate 0 "task-16: --per-project passes when all projects meet threshold" -- \
    --per-project "$DATA/perproject-pass" --threshold 80 \
    --exclude '*TestSupport*'

# The pass dir contains a low-coverage TestSupport file; WITHOUT excluding it
# the gate must FAIL — proves the exclude flag is what makes it pass above.
run_gate 1 "task-16: --per-project without exclude catches the low TestSupport project" -- \
    --per-project "$DATA/perproject-pass" --threshold 80

# Vacuous-pass guard: excluding EVERY project must FAIL, not silently pass.
run_gate 1 "task-16: --per-project with all projects excluded fails (no vacuous pass)" -- \
    --per-project "$DATA/perproject-pass" --threshold 80 \
    --exclude '*'

# grep/sed fallback parity for per-project verdicts.
run_gate_noxmllint 1 "task-16: --per-project (no xmllint) fails when any project is below threshold" -- \
    --per-project "$DATA/perproject" --threshold 80

# ---------------------------------------------------------------------------
# task-18 (DR-5) — per-assembly gating from a single merged Cobertura report
# ---------------------------------------------------------------------------

# RED: merged report has Bifrost.Core at branch-rate 0.50 (< 80) while every
# other assembly clears 80/80 → the gate must FAIL because ANY sub-threshold
# assembly fails the whole run.
run_gate 1 "task-18: --per-assembly fails when one assembly (Bifrost.Core) is below branch threshold" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80

# GREEN: every assembly in the merged report clears 80 line + 80 branch → pass.
run_gate 0 "task-18: --per-assembly passes when every assembly meets line+branch threshold" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80

# Excluding the one failing assembly by NAME flips the failing report to pass —
# proves --exclude matches the <package> name, not a filename.
run_gate 0 "task-18: --per-assembly --exclude on the failing assembly name passes" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --exclude 'Bifrost.Core'

# EXCLUDE env var supplies the same exclusion (whitespace list) as the flag.
EXCLUDE='Bifrost.Core' run_gate 0 "task-18: --per-assembly honors EXCLUDE env exclusion" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80

# Vacuous-pass guard: excluding EVERY assembly must FAIL, not silently pass.
run_gate 1 "task-18: --per-assembly with all assemblies excluded fails (no vacuous pass)" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --exclude 'Bifrost*'

# Mutual exclusivity: --per-assembly cannot be combined with the other modes.
run_gate 1 "task-18: --per-assembly + --coverage-file is rejected (mutually exclusive)" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" \
    --coverage-file "$DATA/line85-branch85.cobertura.xml" --threshold 80

run_gate 1 "task-18: --per-assembly + --per-project is rejected (mutually exclusive)" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" \
    --per-project "$DATA/perproject-pass" --threshold 80

# No mode at all is rejected.
run_gate 1 "task-18: no mode flag is rejected" -- \
    --threshold 80

# Missing merged report file is a clean failure, not a crash.
run_gate 1 "task-18: --per-assembly with a missing report file fails" -- \
    --per-assembly "$DATA/does-not-exist.cobertura.xml" --threshold 80

# --- grep/sed fallback path (xmllint shadowed out of PATH) ------------------
# The per-assembly logic must produce identical verdicts without xmllint.
run_gate_noxmllint 1 "task-18: --per-assembly (no xmllint) fails on sub-threshold assembly" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80

run_gate_noxmllint 0 "task-18: --per-assembly (no xmllint) passes when all assemblies meet threshold" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80

run_gate_noxmllint 0 "task-18: --per-assembly (no xmllint) --exclude flips failing report to pass" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --exclude 'Bifrost.Core'

run_gate_noxmllint 1 "task-18: --per-assembly (no xmllint) all-excluded fails (no vacuous pass)" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --exclude 'Bifrost*'

# ---------------------------------------------------------------------------
# task-21 (issue #21) — per-assembly TIERED thresholds
#
# A risk-tiered floor map ("GLOB = LINE[/BRANCH]", repeatable / via
# ASSEMBLY_THRESHOLDS) lets security/boundary assemblies be held higher than
# host wiring. First matching rule wins; assemblies matching no rule fall back
# to the global --threshold; an EMPTY map reproduces task-18 behavior exactly.
# Fixtures reused: merged-multipackage-pass (all >= 80/80; Scheduling.Core
# 0.92/0.84) and merged-multipackage (Bifrost.Core 0.93 line / 0.50 branch).
# ---------------------------------------------------------------------------

# RAISE: an all-passing report FAILS once a tiered rule lifts one assembly's
# floor above its actual coverage (Scheduling.Core 0.92 line < a 95 floor).
run_gate 1 "task-21: per-assembly tiered rule raising a floor fails an assembly above its actual coverage" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --assembly-threshold '*Scheduling.Core = 95/90'

# LOWER + fallback: the global-80 report FAILS on Bifrost.Core branch 0.50, but
# a tiered rule lowering ONLY Bifrost.Core's branch floor to 40 flips it to PASS
# while every other assembly is still gated at the global 80/80 fallback.
run_gate 0 "task-21: per-assembly tiered rule lowering one assembly's branch floor passes; others use global fallback" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = 80/40'

# Branch IS still gated under a tiered rule: a 60 branch floor on Bifrost.Core
# (branch 0.50) FAILS — proves the lowered-floor pass above is real gating.
run_gate 1 "task-21: per-assembly tiered branch floor still gates branch (Bifrost.Core 0.50 < 60)" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = 80/60'

# LINE-ONLY rule (no BRANCH): host-wiring style "don't chase branch %". A rule
# of "Bifrost.Core = 80" gates line only, so its 0.50 branch is ignored -> PASS.
run_gate 0 "task-21: per-assembly line-only rule skips the branch check (host wiring)" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = 80'

# FIRST-MATCH-WINS: a specific Bifrost.Core rule precedes a broad catch-all that
# would otherwise fail it. Core passes on its specific 80/40; the catch-all
# 99/99 fails the OTHER assemblies -> overall FAIL, proving order precedence.
run_gate 1 "task-21: per-assembly first matching rule wins over a later catch-all" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = 80/40' \
    --assembly-threshold '* = 99/99'

# ENV VAR == FLAG: the same lowering rule supplied via ASSEMBLY_THRESHOLDS
# (newline list, with a '#' comment + blank line to be ignored) -> PASS.
ASSEMBLY_THRESHOLDS=$'# tiered floors\nBifrost.Core = 80/40\n' \
    run_gate 0 "task-21: per-assembly honors the ASSEMBLY_THRESHOLDS env var (comments/blanks ignored)" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80

# EMPTY MAP = PARITY: with no rules, the per-assembly verdict is unchanged from
# task-18 (the all-passing report still PASSES) — the feature is purely additive.
run_gate 0 "task-21: per-assembly with an empty threshold map is parity with task-18 (no drift)" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80

# MALFORMED RULE is a hard error, not a silently dropped floor.
run_gate 1 "task-21: per-assembly malformed rule (no '=') fails fast" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --assembly-threshold 'NoEqualsSign'

run_gate 1 "task-21: per-assembly malformed rule (non-numeric percent) fails fast" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = high/low'

# grep/sed fallback (no xmllint) yields the same tiered verdict.
run_gate_noxmllint 1 "task-21: per-assembly (no xmllint) tiered raise fails an assembly above its floor" -- \
    --per-assembly "$DATA/merged-multipackage-pass.cobertura.xml" --threshold 80 \
    --assembly-threshold '*Scheduling.Core = 95/90'

run_gate_noxmllint 0 "task-21: per-assembly (no xmllint) tiered lower passes with global fallback" -- \
    --per-assembly "$DATA/merged-multipackage.cobertura.xml" --threshold 80 \
    --assembly-threshold 'Bifrost.Core = 80/40'

# ---------------------------------------------------------------------------
# DR-T2 — cross-language (TypeScript / vitest+istanbul) Cobertura
#
# The gate is generic Cobertura: it must read a vitest/istanbul `cobertura`
# report identically to a .NET one. The fixture uses DIRECTORY-style <package>
# names (incl. a nested, slash-containing monorepo path) + an istanbul DOCTYPE
# and per-line <lines> subtree. These cases RED-guard any C#-specific assumption
# creeping into coverage-gate.sh. (Discovery finding F1 — locked under test.)
# ---------------------------------------------------------------------------

# Aggregate default (line-only): line 0.90 >= 80 -> PASS, same as any .NET report.
run_gate 0 "DR-T2: aggregate default passes on TS/istanbul cobertura (line 0.90 >= 80)" -- \
    --coverage-file "$DATA/ts-vitest.cobertura.xml" --threshold 80

# Aggregate default at 95: line 0.90 < 95 -> FAIL.
run_gate 1 "DR-T2: aggregate default fails on TS cobertura when line 0.90 < 95" -- \
    --coverage-file "$DATA/ts-vitest.cobertura.xml" --threshold 95

# Per-assembly (== per-DIRECTORY for TS): both dirs clear 80 line+branch -> PASS.
# Proves the gate parses slash-containing <package> names.
run_gate 0 "DR-T2: --per-assembly passes on TS cobertura (every directory >= 80 line+branch)" -- \
    --per-assembly "$DATA/ts-vitest.cobertura.xml" --threshold 80

# At 85, servers/exarchos-mcp/src branch 0.82 < 85 -> FAIL (one sub-threshold dir).
run_gate 1 "DR-T2: --per-assembly fails when a TS directory branch (0.82) is below 85" -- \
    --per-assembly "$DATA/ts-vitest.cobertura.xml" --threshold 85

# Excluding the failing directory BY ITS SLASH-CONTAINING NAME flips fail -> pass.
run_gate 0 "DR-T2: --per-assembly --exclude on a slash-containing directory name passes" -- \
    --per-assembly "$DATA/ts-vitest.cobertura.xml" --threshold 85 \
    --exclude 'servers/exarchos-mcp/src'

# grep/sed fallback (no xmllint) yields the same verdict on directory names.
run_gate_noxmllint 1 "DR-T2: --per-assembly (no xmllint) fails on sub-threshold TS directory" -- \
    --per-assembly "$DATA/ts-vitest.cobertura.xml" --threshold 85

echo
echo "=== $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
