"""The command line: exit codes, one line per violation, and annotations inside Actions only."""

from __future__ import annotations

import contextlib
import io
import unittest
from collections.abc import Mapping

from workflow_hygiene.__main__ import main
from workflow_hygiene.errors import EXIT_INDETERMINATE, EXIT_PASS, EXIT_VIOLATION

from .consumer import CI, FILES
from .support import actions_environment, mutate, repo

SEEDED = mutate(FILES, CI, "    timeout-minutes: 15\n", "")
SEEDED_LINE = "ci.yml:build: has no timeout-minutes, so a hung job runs for the 360-minute default"


def run(files: Mapping[str, str], **environment: str) -> tuple[int, list[str]]:
    output = io.StringIO()
    with repo(files) as root, actions_environment(**environment), contextlib.redirect_stdout(output):
        code = main(["--root", str(root)])
    return code, output.getvalue().splitlines()


class CommandTests(unittest.TestCase):
    def test_clean_tree_passes(self) -> None:
        code, lines = run(FILES)
        self.assertEqual(code, EXIT_PASS)
        self.assertEqual(lines[-1], "workflow-hygiene: PASS over 4 workflow(s), 7 job(s), 1 exempted")
        self.assertIn("exempt: nightly.yml:soak: the soak test is bounded by its own harness deadline", lines)

    def test_violation_prints_one_line_and_exits_1(self) -> None:
        code, lines = run(SEEDED)
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertIn(SEEDED_LINE, lines)
        self.assertFalse(any(line.startswith("::") for line in lines))
        self.assertTrue(lines[-1].startswith("workflow-hygiene: FAIL (1 violation(s))"))

    def test_violation_is_annotated_inside_actions(self) -> None:
        code, lines = run(SEEDED, GITHUB_ACTIONS="true")
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertIn(SEEDED_LINE, lines)
        self.assertIn("::error title=workflow-hygiene::" + SEEDED_LINE, lines)

    def test_indeterminate_exits_2(self) -> None:
        cases: tuple[tuple[str, Mapping[str, str]], ...] = (
            ("zero workflow files", {"README.md": "x"}),
            ("unparseable YAML", {**FILES, CI: "on: [pull_request\n"}),
            ("unreadable exemption file", {**FILES, ".github/workflow-hygiene.toml": "[exempt\n"}),
        )
        for description, files in cases:
            with self.subTest(description):
                code, lines = run(files, GITHUB_ACTIONS="true")
                self.assertEqual(code, EXIT_INDETERMINATE)
                self.assertTrue(any(line.startswith("::error title=workflow-hygiene INDETERMINATE::") for line in lines))

    def test_missing_root_exits_2(self) -> None:
        with repo({}) as root, actions_environment(), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--root", str(root / "absent")]), EXIT_INDETERMINATE)


if __name__ == "__main__":
    unittest.main()
