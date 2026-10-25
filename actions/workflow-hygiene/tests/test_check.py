"""Both rules and the exemption file, from a green consumer baseline plus one hostile edit at a time."""

from __future__ import annotations

import unittest
from collections.abc import Mapping

from workflow_hygiene.check import Report, run_check
from workflow_hygiene.errors import Indeterminate

from .consumer import CI, CONFIG, FILES, GATE, NIGHTLY, SHARED_CONCURRENCY
from .support import mutate, repo, without

CANCEL = "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n"


def check(files: Mapping[str, str]) -> Report:
    with repo(files) as root:
        return run_check(root)


def locations(report: Report) -> list[str]:
    return [finding.location for finding in report.violations]


def pr_workflow(on: str, *, concurrency: str = "", job_concurrency: str = "") -> dict[str, str]:
    return {
        ".github/workflows/w.yml": (
            f"on: {on}\n{concurrency}jobs:\n  build:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n{job_concurrency}"
            "    steps:\n      - run: echo\n"
        )
    }


# (description, file, old text, new text, expected violation locations)
HOSTILE: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("workflow-level concurrency removed", CI, SHARED_CONCURRENCY, "", ("ci.yml:*",)),
    ("cancel-in-progress false", CI, CANCEL, "  cancel-in-progress: false\n", ("ci.yml:*",)),
    ("cancel-in-progress 'false'", CI, CANCEL, "  cancel-in-progress: 'false'\n", ("ci.yml:*",)),
    ("cancel-in-progress ${{ false }}", CI, CANCEL, "  cancel-in-progress: ${{ false }}\n", ("ci.yml:*",)),
    ("cancel-in-progress dropped", CI, CANCEL, "", ("ci.yml:*",)),
    ("one job loses its job-level concurrency", GATE, "      cancel-in-progress: 'true'\n", "", ("gate.yaml:*",)),
    ("one job-level cancel set to false", GATE, "      cancel-in-progress: true\n", "      cancel-in-progress: false\n",
     ("gate.yaml:*",)),
    ("timeout removed", CI, "    timeout-minutes: 15\n", "", ("ci.yml:build",)),
    ("timeout zero", CI, "timeout-minutes: 15", "timeout-minutes: 0", ("ci.yml:build",)),
    ("timeout not a number", CI, "timeout-minutes: 15", "timeout-minutes: soon", ("ci.yml:build",)),
    ("timeout boolean", CI, "timeout-minutes: 15", "timeout-minutes: true", ("ci.yml:build",)),
    ("reusable call turned into an inline job", CI, "    uses: ./.github/workflows/reusable.yml\n",
     "    runs-on: ubuntu-latest\n    steps:\n      - run: echo lint\n", ("ci.yml:lint",)),
    ("exemption reason empty", CONFIG, '"the soak test is bounded by its own harness deadline"', '"  "',
     ("nightly.yml:soak", ".github/workflow-hygiene.toml:nightly.yml:soak")),
    ("exemption reason not a string", CONFIG, '"the soak test is bounded by its own harness deadline"', "true",
     ("nightly.yml:soak", ".github/workflow-hygiene.toml:nightly.yml:soak")),
    ("exemption key malformed", CONFIG, '"nightly.yml:soak"', '"nightly:soak"',
     ("nightly.yml:soak", ".github/workflow-hygiene.toml:nightly:soak")),
    ("exemption covers a job that now has a timeout", NIGHTLY, "    runs-on: ubuntu-latest\n",
     "    runs-on: ubuntu-latest\n    timeout-minutes: 30\n", (".github/workflow-hygiene.toml:nightly.yml:soak",)),
    ("exemption names a renamed job", NIGHTLY, "  soak:\n", "  endurance:\n",
     ("nightly.yml:endurance", ".github/workflow-hygiene.toml:nightly.yml:soak")),
)


class BaselineTests(unittest.TestCase):
    def test_consumer_baseline_passes_and_sees_every_job(self) -> None:
        report = check(FILES)
        self.assertEqual(report.violations, [])
        self.assertEqual(report.workflows, 4)
        self.assertEqual(report.jobs, 7)
        self.assertEqual([(finding.location, reason) for finding, reason in report.exempted],
                         [("nightly.yml:soak", "the soak test is bounded by its own harness deadline")])

    def test_hostile_edits_are_refused(self) -> None:
        for description, path, old, new, expected in HOSTILE:
            with self.subTest(description):
                self.assertEqual(locations(check(mutate(FILES, path, old, new))), list(expected))

    def test_seeded_violation_one_missing_timeout_fails(self) -> None:
        seeded = mutate(FILES, CI, "    timeout-minutes: 30\n", "")
        report = check(seeded)
        self.assertFalse(report.passed)
        self.assertEqual(
            [finding.render() for finding in report.violations],
            ["ci.yml:test: has no timeout-minutes, so a hung job runs for the 360-minute default"],
        )


class ConcurrencyRuleTests(unittest.TestCase):
    def test_every_pull_request_on_form_needs_concurrency(self) -> None:
        for on in (
            "pull_request",
            "pull_request_target",
            "[push, pull_request]",
            "{pull_request: {types: [opened]}, push: {branches: [main]}}",
            "{pull_request_target: null}",
        ):
            with self.subTest(on=on):
                report = check(pr_workflow(on))
                self.assertEqual(locations(report), ["w.yml:*"])
                self.assertIn("job(s) build", report.violations[0].message)
                self.assertTrue(check(pr_workflow(on, concurrency=SHARED_CONCURRENCY)).passed)

    def test_quoted_on_key_is_read_like_the_bare_one(self) -> None:
        files = {".github/workflows/w.yml": pr_workflow("pull_request")[".github/workflows/w.yml"].replace("on:", '"on":', 1)}
        self.assertEqual(locations(check(files)), ["w.yml:*"])

    def test_non_pull_request_workflows_need_no_concurrency(self) -> None:
        for on in ("push", "[push, workflow_dispatch]", "{schedule: [{cron: '0 0 * * *'}]}", "workflow_call", "merge_group"):
            with self.subTest(on=on):
                self.assertTrue(check(pr_workflow(on)).passed)

    def test_job_level_concurrency_on_every_job_passes(self) -> None:
        job = "    concurrency:\n      group: g-${{ github.ref }}\n      cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n"
        self.assertTrue(check(pr_workflow("pull_request", job_concurrency=job)).passed)

    def test_job_level_group_without_cancel_fails(self) -> None:
        job = "    concurrency:\n      group: g-${{ github.ref }}\n"
        self.assertEqual(locations(check(pr_workflow("pull_request", job_concurrency=job))), ["w.yml:*"])

    def test_string_concurrency_never_cancels(self) -> None:
        self.assertEqual(
            locations(check(pr_workflow("pull_request", concurrency="concurrency: ci-${{ github.ref }}\n"))), ["w.yml:*"]
        )

    def test_reusable_caller_in_a_pull_request_workflow_still_needs_cancellation(self) -> None:
        files = {".github/workflows/w.yml": "on: pull_request\njobs:\n  call:\n    uses: ./.github/workflows/r.yml\n"}
        self.assertEqual(locations(check(files)), ["w.yml:*"])


class ExemptionTests(unittest.TestCase):
    def test_workflow_wide_exemption_covers_only_the_concurrency_rule(self) -> None:
        files = {
            **pr_workflow("pull_request"),
            CONFIG: '[exempt]\n"w.yml:*" = "a started deploy must finish"\n',
        }
        report = check(files)
        self.assertTrue(report.passed)
        self.assertEqual([finding.location for finding, _ in report.exempted], ["w.yml:*"])

        no_timeout = mutate(files, ".github/workflows/w.yml", "    timeout-minutes: 5\n", "")
        self.assertEqual(locations(check(no_timeout)), ["w.yml:build"])

    def test_job_exemption_does_not_cover_the_concurrency_rule(self) -> None:
        files = {
            **pr_workflow("pull_request"),
            CONFIG: '[exempt]\n"w.yml:build" = "reason"\n',
        }
        self.assertEqual(locations(check(files)), ["w.yml:*", ".github/workflow-hygiene.toml:w.yml:build"])

    def test_stale_exemptions_name_what_went_missing(self) -> None:
        cases = (
            ('"gone.yml:build" = "r"', "workflow gone.yml does not exist"),
            ('"ci.yml:deploy" = "r"', "job deploy does not exist in ci.yml"),
            ('"ci.yml:*" = "r"', "it matches no violation"),
            ('"nightly.yml:*" = "r"', "it matches no violation"),
        )
        for entry, fragment in cases:
            with self.subTest(entry):
                files = mutate(FILES, CONFIG, "[exempt]\n", f"[exempt]\n{entry}\n")
                report = check(files)
                self.assertEqual(len(report.violations), 1)
                self.assertIn("stale exemption", report.violations[0].message)
                self.assertIn(fragment, report.violations[0].message)

    def test_no_exemption_file_means_no_exemptions(self) -> None:
        self.assertEqual(locations(check(without(FILES, CONFIG))), ["nightly.yml:soak"])

    def test_empty_exempt_table_is_allowed(self) -> None:
        files = mutate(FILES, CONFIG, '"nightly.yml:soak" = "the soak test is bounded by its own harness deadline"\n', "")
        self.assertEqual(locations(check(files)), ["nightly.yml:soak"])

    def test_unreadable_exemption_file_is_indeterminate(self) -> None:
        for description, text in (
            ("not TOML", "[exempt\n"),
            ("misspelled table", '[exemptions]\n"nightly.yml:soak" = "r"\n'),
            ("exempt not a table", 'exempt = "nightly.yml:soak"\n'),
        ):
            with self.subTest(description), self.assertRaises(Indeterminate):
                check({**FILES, CONFIG: text})


if __name__ == "__main__":
    unittest.main()
