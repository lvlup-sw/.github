from __future__ import annotations

import json
import tomllib
import unittest

from ci_lanes.errors import Indeterminate
from ci_lanes.manifest import Manifest, parse_manifest
from ci_lanes.plan import changed_paths, plan_for_event, plan_for_files

from .consumer import FILES, MANIFEST
from .support import commit, git, git_repo


def manifest() -> Manifest:
    return parse_manifest(tomllib.loads(MANIFEST), ".github/ci-lanes.toml")


class PlanTests(unittest.TestCase):
    def test_diff_selects_only_matching_lanes(self) -> None:
        plan = plan_for_files(manifest(), ["docs/readme.md"])
        self.assertEqual(json.loads(plan.lanes_json()), {"build": "false", "docs": "true", "infra": "false", "lint": "false"})
        self.assertEqual(plan.changed_count, 1)

    def test_shared_path_selects_every_lane_that_reads_it(self) -> None:
        plan = plan_for_files(manifest(), ["src/app.cs"])
        self.assertTrue(plan.relevant("build"))
        self.assertTrue(plan.relevant("lint"))
        self.assertFalse(plan.relevant("docs"))

    def test_a_lane_workflow_edit_selects_that_lane(self) -> None:
        plan = plan_for_files(manifest(), [".github/workflows/matrix.yml"])
        self.assertTrue(plan.relevant("infra"))
        self.assertFalse(plan.relevant("build"))

    def test_manifest_edit_selects_every_lane(self) -> None:
        plan = plan_for_files(manifest(), [".github/ci-lanes.toml"])
        self.assertTrue(all(decision.relevant for decision in plan.decisions))

    def test_unmatched_change_selects_nothing(self) -> None:
        plan = plan_for_files(manifest(), ["README.md"])
        self.assertFalse(any(decision.relevant for decision in plan.decisions))

    def test_non_pull_request_events_run_every_lane(self) -> None:
        for event in ("push", "merge_group", "schedule", "workflow_dispatch", "pull_request_target"):
            with self.subTest(event=event):
                plan = plan_for_event(manifest(), event, None)
                self.assertTrue(all(decision.relevant for decision in plan.decisions))

    def test_indeterminate_inputs(self) -> None:
        cases: tuple[tuple[str, str, list[str] | None], ...] = (
            ("empty event", "", ["docs/readme.md"]),
            ("pull request without changes", "pull_request", None),
            ("empty change", "pull_request", []),
            ("absolute path", "pull_request", ["/etc/passwd"]),
            ("parent path", "pull_request", ["docs/../src/app.cs"]),
        )
        for description, event, changed in cases:
            with self.subTest(description), self.assertRaises(Indeterminate):
                plan_for_event(manifest(), event, changed)

    def test_unknown_lane_is_indeterminate(self) -> None:
        with self.assertRaises(Indeterminate):
            plan_for_files(manifest(), ["docs/readme.md"]).relevant("site")


class ChangedPathsTests(unittest.TestCase):
    def test_lists_three_dot_diff(self) -> None:
        with git_repo(FILES) as repo:
            base = git(repo, "rev-parse", "HEAD")
            head = commit(repo, {"docs/readme.md": "changed\n", "infra/modules/a/main.tf": "# changed\n"})
            self.assertEqual(changed_paths(repo, base, head), ("docs/readme.md", "infra/modules/a/main.tf"))

    def test_rename_lists_old_and_new_path(self) -> None:
        with git_repo(FILES) as repo:
            base = git(repo, "rev-parse", "HEAD")
            git(repo, "mv", "src/app.cs", "docs/app.cs")
            git(repo, "commit", "-q", "-m", "move")
            head = git(repo, "rev-parse", "HEAD")
            paths = changed_paths(repo, base, head)
            self.assertEqual(paths, ("docs/app.cs", "src/app.cs"))
            self.assertTrue(plan_for_files(manifest(), paths).relevant("build"))

    def test_bad_or_missing_commits_are_indeterminate(self) -> None:
        with git_repo(FILES) as repo:
            head = git(repo, "rev-parse", "HEAD")
            for base in ("", "HEAD", head[:12], head.upper(), "0" * 40):
                with self.subTest(base=base), self.assertRaises(Indeterminate):
                    changed_paths(repo, base, head)


if __name__ == "__main__":
    unittest.main()
