from __future__ import annotations

import unittest
from collections.abc import Mapping

from ci_lanes.check import CheckResult, canonical_enable, canonical_skip, run_check
from ci_lanes.errors import Indeterminate
from ci_lanes.manifest import load_manifest

from .consumer import FILES
from .support import git_repo, mutate

CI = ".github/workflows/ci.yml"
MATRIX = ".github/workflows/matrix.yml"
DOCS = ".github/workflows/docs.yml"
MANIFEST = ".github/ci-lanes.toml"

BUILD_SKIP = canonical_skip("plan", "build")


def check(files: Mapping[str, str]) -> CheckResult:
    with git_repo(files) as repo:
        return run_check(repo, load_manifest(repo, MANIFEST))


# (description, file, old text, new text, fragment of the expected violation)
HOSTILE: tuple[tuple[str, str, str, str, str], ...] = (
    ("targeted job disabled outright", CI, f"if: {BUILD_SKIP}", "if: false", "must carry exactly if:"),
    ("targeted job fails open on a missing lane", CI, f"if: {BUILD_SKIP}",
     "if: ${{ fromJSON(needs.plan.outputs.lanes).build == 'true' }}", "must carry exactly if:"),
    ("targeted job trusts a failed planner", CI, f"if: {BUILD_SKIP}",
     "if: ${{ always() && fromJSON(needs.plan.outputs.lanes).build != 'false' }}", "must carry exactly if:"),
    ("targeted job swallows its failure", CI, "  build:\n    needs: plan\n",
     "  build:\n    needs: plan\n    continue-on-error: true\n", "must not carry continue-on-error"),
    ("targeted job reads a lane without needing the planner", CI, "  build:\n    needs: plan\n", "  build:\n",
     "reads planner lanes but does not need plan"),
    ("targeted job reads a lane declared for another workflow", CI, "fromJSON(needs.plan.outputs.lanes).build",
     "fromJSON(needs.plan.outputs.lanes).docs", "which the manifest does not declare for ci.yml"),
    ("reusable caller enabled unconditionally", CI, f"enabled: {canonical_enable('plan', 'lint')}", "enabled: true",
     "belongs to exactly one lane"),
    ("reusable caller licenses a skip on anything but 'false'", CI, f"enabled: {canonical_enable('plan', 'lint')}",
     "enabled: ${{ fromJSON(needs.plan.outputs.lanes).lint == 'true' }}", "must pass exactly enabled:"),
    ("matrix job skipped without a gate", MANIFEST, '[gates.infra-gate]\nworkflow = "matrix.yml"\njobs = { validate = "infra" }\n', "",
     "cover it with a gate"),
    ("gate not forced to run", MATRIX, "    if: always()\n", "    if: success()\n", "must run with if: always()"),
    ("gate does not need a covered job", MATRIX, "needs: [plan, validate]", "needs: [plan]", "must need exactly"),
    ("gate judges another gate", MATRIX, "gate: infra-gate", "gate: other-gate", "mode: verdict, gate: infra-gate"),
    ("gate swallows its failure", MATRIX, "  infra-gate:\n", "  infra-gate:\n    continue-on-error: true\n",
     "a gate must not carry continue-on-error"),
    ("planner made conditional", CI, "  plan:\n", "  plan:\n    if: github.event_name == 'pull_request'\n",
     "must not be conditional"),
    ("planner checks out shallow history", CI, "fetch-depth: 0\n      - id: plan", "fetch-depth: 1\n      - id: plan",
     "full history"),
    ("planner exposes the wrong output", CI, "lanes: ${{ steps.plan.outputs.lanes }}", "lanes: ${{ steps.other.outputs.lanes }}",
     "outputs.lanes exactly"),
    ("planner step swallows its failure", CI, "        uses: ./actions/ci-lanes\n  build:",
     "        uses: ./actions/ci-lanes\n        continue-on-error: true\n  build:", "ci-lanes step must not carry continue-on-error"),
    ("lane glob matches nothing", MANIFEST, 'paths = ["docs/**"]', 'paths = ["documentation/**"]', "matches no tracked file"),
    ("dead lane", MANIFEST, "[lanes.docs]", '[lanes.orphan]\nworkflows = ["ci.yml"]\npaths = ["src/**"]\n\n[lanes.docs]',
     "lane orphan: no job or step"),
    ("job names a file outside its lane", CI, "run: bash scripts/build.sh src/app.cs",
     "run: bash scripts/build.sh src/app.cs scripts/audit.sh", "names scripts/audit.sh"),
    ("job names a directory outside its lane", CI, "run: bash scripts/build.sh src/app.cs",
     "run: bash scripts/build.sh src/app.cs && ls infra/modules/", "names directory infra/modules/"),
    ("stale exemption", MANIFEST, 'paths = ["src/**", "scripts/build.sh"]',
     'paths = ["src/**", "scripts/build.sh"]\nexempt_paths = { "scripts/gone.sh" = "retired" }', "no longer exists"),
    ("fixture no longer replays", MANIFEST, "expect = { build = false,", "expect = { build = true,",
     "fixture 'docs only': lane build is false, expected true"),
    ("in-step selector names an undeclared lane", DOCS, "lane: docs", "lane: doc", "in-step selector names lane 'doc'"),
    ("in-step selector plans over shallow history", DOCS, "fetch-depth: 0", "fetch-depth: 1", "must follow a full-history checkout"),
    ("undeclared job runs a verdict", MATRIX, "  infra-gate:\n", "  judge:\n", "only a gate the manifest declares"),
)


class CheckTests(unittest.TestCase):
    def test_baseline_is_clean_and_not_vacuous(self) -> None:
        result = check(FILES)
        self.assertEqual(result.violations, [])
        self.assertGreaterEqual(result.assertions, 40)

    def test_hostile_edits_are_refused(self) -> None:
        for description, path, old, new, fragment in HOSTILE:
            with self.subTest(description):
                result = check(mutate(FILES, path, old, new))
                self.assertTrue(
                    any(fragment in violation for violation in result.violations),
                    f"expected a violation containing {fragment!r}, got {result.violations}",
                )

    def test_exemption_admits_a_named_path(self) -> None:
        files = mutate(FILES, CI, "run: bash scripts/build.sh src/app.cs", "run: bash scripts/build.sh src/app.cs scripts/audit.sh")
        files = mutate(files, MANIFEST, 'paths = ["src/**", "scripts/build.sh"]',
                       'paths = ["src/**", "scripts/build.sh"]\nexempt_paths = { "scripts/audit.sh" = "prints a banner only" }')
        self.assertEqual(check(files).violations, [])

    def test_run_paths_resolve_against_the_working_directory(self) -> None:
        # Under working-directory docs, `README.md` is docs/README.md (untracked), not the
        # repository-root README.md that lane docs does not match.
        files = mutate(FILES, DOCS, "  docs:\n    runs-on: ubuntu-latest\n",
                       "  docs:\n    runs-on: ubuntu-latest\n    defaults:\n      run:\n        working-directory: docs\n")
        clean = mutate(files, DOCS, "run: cat docs/readme.md", "run: cat readme.md README.md")
        self.assertEqual(check(clean).violations, [])
        escaping = mutate(files, DOCS, "run: cat docs/readme.md", "run: cat readme.md ../scripts/audit.sh")
        self.assertTrue(any("names scripts/audit.sh" in violation for violation in check(escaping).violations))

    def test_duplicate_yaml_key_is_indeterminate(self) -> None:
        files = mutate(FILES, CI, "  build:\n    needs: plan\n", "  build:\n    needs: plan\n    needs: plan\n")
        with self.assertRaises(Indeterminate) as caught:
            check(files)
        self.assertIn("duplicate mapping key", str(caught.exception))

    def test_workflow_without_jobs_is_indeterminate(self) -> None:
        files = dict(FILES)
        files[DOCS] = "name: Docs\non: pull_request\n"
        with self.assertRaises(Indeterminate):
            check(files)


if __name__ == "__main__":
    unittest.main()
