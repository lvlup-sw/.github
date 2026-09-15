from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ci_lanes.__main__ import main
from ci_lanes.errors import EXIT_INDETERMINATE, EXIT_PASS, EXIT_VIOLATION

from .consumer import FILES
from .support import actions_environment, commit, git, git_repo, mutate, read_outputs


def run(*argv: str) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return main(list(argv))


class PlanCommandTests(unittest.TestCase):
    def test_pull_request_publishes_lanes_and_relevant(self) -> None:
        with git_repo(FILES) as repo, tempfile.TemporaryDirectory() as scratch:
            base = git(repo, "rev-parse", "HEAD")
            head = commit(repo, {"docs/readme.md": "changed\n"})
            output = Path(scratch) / "output"
            summary = Path(scratch) / "summary"
            with actions_environment(GITHUB_ACTIONS="true", GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary)):
                code = run("plan", "--repo", str(repo), "--event", "pull_request", "--base", base, "--head", head, "--lane", "docs")
            self.assertEqual(code, EXIT_PASS)
            outputs = read_outputs(output)
            self.assertEqual(json.loads(outputs["lanes"]), {"build": "false", "docs": "true", "infra": "false", "lint": "false"})
            self.assertEqual(outputs["relevant"], "true")
            self.assertIn("`docs/readme.md`", summary.read_text(encoding="utf-8"))

    def test_push_runs_every_lane(self) -> None:
        with git_repo(FILES) as repo, tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "output"
            with actions_environment(GITHUB_OUTPUT=str(output), GITHUB_EVENT_NAME="push"):
                self.assertEqual(run("plan", "--repo", str(repo)), EXIT_PASS)
            self.assertEqual(set(json.loads(read_outputs(output)["lanes"]).values()), {"true"})

    def test_indeterminate_plans_exit_2(self) -> None:
        with git_repo(FILES) as repo, tempfile.TemporaryDirectory() as scratch:
            head = git(repo, "rev-parse", "HEAD")
            output = str(Path(scratch) / "output")
            cases: tuple[tuple[str, dict[str, str], tuple[str, ...]], ...] = (
                ("empty diff", {"GITHUB_OUTPUT": output}, ("--event", "pull_request", "--base", head, "--head", head)),
                ("missing SHAs", {"GITHUB_OUTPUT": output}, ("--event", "pull_request")),
                ("unknown lane", {"GITHUB_OUTPUT": output}, ("--event", "push", "--lane", "site")),
                ("no event", {"GITHUB_OUTPUT": output}, ()),
                ("inside Actions with nowhere to publish", {"GITHUB_ACTIONS": "true"}, ("--event", "push")),
                ("missing manifest", {"GITHUB_OUTPUT": output}, ("--event", "push", "--manifest", ".github/absent.toml")),
            )
            for description, environment, arguments in cases:
                with self.subTest(description), actions_environment(**environment):
                    self.assertEqual(run("plan", "--repo", str(repo), *arguments), EXIT_INDETERMINATE)


class VerdictCommandTests(unittest.TestCase):
    def test_exit_codes(self) -> None:
        licensed = json.dumps({"plan": {"result": "success", "outputs": {"lanes": '{"infra":"false"}'}}, "validate": {"result": "skipped"}})
        unlicensed = json.dumps({"plan": {"result": "failure", "outputs": {}}, "validate": {"result": "skipped"}})
        with git_repo(FILES) as repo:
            for description, payload, expected in (
                ("licensed skip", licensed, EXIT_PASS),
                ("skip after planner failure", unlicensed, EXIT_VIOLATION),
                ("unreadable needs", "not json", EXIT_INDETERMINATE),
            ):
                with self.subTest(description), actions_environment(CI_LANES_NEEDS=payload):
                    self.assertEqual(run("verdict", "--repo", str(repo), "--gate", "infra-gate"), expected)


class CheckCommandTests(unittest.TestCase):
    def test_exit_codes(self) -> None:
        with git_repo(FILES) as repo, actions_environment():
            self.assertEqual(run("check", "--repo", str(repo)), EXIT_PASS)
        broken = mutate(FILES, ".github/workflows/ci.yml", "run: bash scripts/build.sh src/app.cs", "run: bash scripts/build.sh scripts/audit.sh")
        with git_repo(broken) as repo, actions_environment():
            self.assertEqual(run("check", "--repo", str(repo)), EXIT_VIOLATION)


if __name__ == "__main__":
    unittest.main()
