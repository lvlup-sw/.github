"""The command line: exit codes, the event file, author skips, git-backed markers and annotations."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

from pr_body.__main__ import main
from pr_body.errors import EXIT_INDETERMINATE, EXIT_PASS, EXIT_VIOLATION

from .consumer import BODY, CLEAN_BODY, FILES, GOLDEN_MARKER, GOLDEN_PATH, MIRROR, TEMPLATE
from .support import actions_environment, repo, write_files

EVENT = "event.json"
SEEDED_BODY = CLEAN_BODY.replace("None.\n", "None.\n\n## Test Plan\n\n- [ ] run it\n")


def event(body: str | None, *, author: str = "octocat", base: str = "", head: str = "") -> str:
    pull = {"body": body, "user": {"login": author}, "base": {"sha": base}, "head": {"sha": head}}
    return json.dumps({"pull_request": pull})


def run(files: Mapping[str, str], extra: Sequence[str], **environment: str) -> tuple[int, list[str]]:
    output = io.StringIO()
    with repo(files) as root, actions_environment(**environment), contextlib.redirect_stdout(output):
        arguments = [arg.replace("{root}", str(root)) for arg in extra]
        code = main(["--root", str(root), "--template", TEMPLATE, *arguments])
    return code, output.getvalue().splitlines()


def from_event(body: str | None, *extra: str, author: str = "octocat", **environment: str) -> tuple[int, list[str]]:
    files = {**FILES, EVENT: event(body, author=author)}
    return run(files, ["--event-file", f"{{root}}/{EVENT}", *extra], **environment)


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments],
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()


class CommandTests(unittest.TestCase):
    def test_clean_body_passes_with_a_denominator(self) -> None:
        code, lines = from_event(CLEAN_BODY, "--same-as", MIRROR)
        self.assertEqual(code, EXIT_PASS)
        self.assertRegex(lines[-1], r"^pr-body: PASS over 5 template heading\(s\), \d+ word\(s\) \(cap 250\), 1 mirror\(s\)$")

    def test_violation_prints_one_line_and_exits_1(self) -> None:
        code, lines = from_event(SEEDED_BODY)
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertEqual([line for line in lines if line.startswith("headings:")], [
            "headings: line 31: '## Test Plan' is not a template heading; use only ## Background, "
            "## Design Decisions, ## Changes, ## Verification Performed, ## Post-Merge Operations"
        ])
        self.assertFalse(any(line.startswith("::") for line in lines))
        self.assertTrue(lines[-1].startswith("pr-body: FAIL (1 violation(s))"))

    def test_violation_is_annotated_inside_actions(self) -> None:
        code, lines = from_event(SEEDED_BODY, GITHUB_ACTIONS="true")
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertTrue(any(line.startswith("::error title=pr-body::headings: line 31:") for line in lines))

    def test_a_null_body_fails_every_heading(self) -> None:
        code, lines = from_event(None)
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertEqual(sum(1 for line in lines if line.endswith("is missing")), 5)

    def test_skipped_author_passes_without_reading_the_body(self) -> None:
        code, lines = from_event(SEEDED_BODY, "--skip-authors", "dependabot[bot]\nrenovate[bot]", author="renovate[bot]")
        self.assertEqual(code, EXIT_PASS)
        self.assertEqual(lines, ["pr-body: SKIP, the author renovate[bot] is in skip-authors"])

    def test_body_file(self) -> None:
        code, _ = run(FILES, ["--body-file", f"{{root}}/{BODY}"])
        self.assertEqual(code, EXIT_PASS)

    def test_body_file_marker_with_changed_files_file(self) -> None:
        files = {**FILES, "changed.txt": f"src/a.ts\n{GOLDEN_PATH}/x.json\n"}
        code, lines = run(files, [
            "--body-file", f"{{root}}/{BODY}", "--marker", GOLDEN_MARKER,
            "--marker-paths", GOLDEN_PATH, "--changed-files-file", "{root}/changed.txt",
        ])
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertTrue(lines[-1].endswith("1 marker path(s) changed"))

    def test_indeterminate_exits_2(self) -> None:
        cases: tuple[tuple[str, Mapping[str, str], list[str]], ...] = (
            ("event without pull_request", {**FILES, EVENT: "{}"}, ["--event-file", f"{{root}}/{EVENT}"]),
            ("event that is not JSON", {**FILES, EVENT: "{"}, ["--event-file", f"{{root}}/{EVENT}"]),
            ("marker without paths", FILES, ["--body-file", f"{{root}}/{BODY}", "--marker", GOLDEN_MARKER]),
            ("paths without marker", FILES, ["--body-file", f"{{root}}/{BODY}", "--marker-paths", GOLDEN_PATH]),
            ("body-file marker without a changed list", FILES,
             ["--body-file", f"{{root}}/{BODY}", "--marker", GOLDEN_MARKER, "--marker-paths", GOLDEN_PATH]),
            ("max-words that is not a number", FILES, ["--body-file", f"{{root}}/{BODY}", "--max-words", "lots"]),
            ("template with no heading", {**FILES, TEMPLATE: "Write well.\n"}, ["--body-file", f"{{root}}/{BODY}"]),
        )
        for description, files, extra in cases:
            with self.subTest(description):
                code, lines = run(files, extra, GITHUB_ACTIONS="true")
                self.assertEqual(code, EXIT_INDETERMINATE)
                self.assertTrue(any(line.startswith("::error title=pr-body INDETERMINATE::") for line in lines))

    def test_missing_root_exits_2(self) -> None:
        with repo({}) as root, actions_environment(), contextlib.redirect_stdout(io.StringIO()):
            code = main(["--root", str(root / "absent"), "--template", TEMPLATE, "--body-file", "x"])
        self.assertEqual(code, EXIT_INDETERMINATE)


class GitMarkerTests(unittest.TestCase):
    """The marker rule reads ``git diff base...head`` from a real repository, as the action does."""

    def scenario(self, body: str, *, fixture_change: bool) -> tuple[int, list[str]]:
        output = io.StringIO()
        with repo(FILES) as root, actions_environment(), contextlib.redirect_stdout(output):
            git(root, "init", "--quiet", "--initial-branch=main")
            git(root, "add", "-A")
            git(root, "commit", "--quiet", "-m", "base")
            base = git(root, "rev-parse", "HEAD")
            changed = f"{GOLDEN_PATH}/golden.json" if fixture_change else "src/app.ts"
            write_files(root, {changed: "{}\n"})
            git(root, "add", "-A")
            git(root, "commit", "--quiet", "-m", "head")
            head = git(root, "rev-parse", "HEAD")
            event_file = root.parent / f"{root.name}-event.json"
            event_file.write_text(event(body, base=base, head=head), encoding="utf-8")
            try:
                code = main([
                    "--root", str(root), "--template", TEMPLATE, "--event-file", str(event_file),
                    "--marker", GOLDEN_MARKER, "--marker-paths", f"{GOLDEN_PATH}/",
                ])
            finally:
                event_file.unlink()
        return code, output.getvalue().splitlines()

    def test_fixture_change_without_marker_fails(self) -> None:
        code, lines = self.scenario(CLEAN_BODY, fixture_change=True)
        self.assertEqual(code, EXIT_VIOLATION)
        self.assertTrue(any(line.startswith("marker:") for line in lines))

    def test_fixture_change_with_marker_passes(self) -> None:
        body = CLEAN_BODY.replace("Closes #12\n", f"Closes #12\n\n{GOLDEN_MARKER} the shape changed.\n")
        code, lines = self.scenario(body, fixture_change=True)
        self.assertEqual(code, EXIT_PASS, lines)
        self.assertTrue(lines[-1].endswith("1 marker path(s) changed"))

    def test_other_change_needs_no_marker(self) -> None:
        code, lines = self.scenario(CLEAN_BODY, fixture_change=False)
        self.assertEqual(code, EXIT_PASS, lines)
        self.assertTrue(lines[-1].endswith("0 marker path(s) changed"))

    def test_an_unknown_base_commit_exits_2(self) -> None:
        files = {**FILES, EVENT: event(CLEAN_BODY, base="0" * 40, head="1" * 40)}
        with repo(files) as root, actions_environment(), contextlib.redirect_stdout(io.StringIO()):
            git(root, "init", "--quiet")
            code = main([
                "--root", str(root), "--template", TEMPLATE, "--event-file", str(root / EVENT),
                "--marker", GOLDEN_MARKER, "--marker-paths", GOLDEN_PATH,
            ])
        self.assertEqual(code, EXIT_INDETERMINATE)


if __name__ == "__main__":
    unittest.main()
