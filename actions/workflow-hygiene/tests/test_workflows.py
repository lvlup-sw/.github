"""Reading workflows: trigger forms, cancel-in-progress truthiness, and fail-closed discovery."""

from __future__ import annotations

import textwrap
import unittest

import yaml

from workflow_hygiene.errors import Indeterminate
from workflow_hygiene.workflows import cancels_in_progress, discover, load_workflow, triggers

from .support import repo


def parse(text: str) -> dict[object, object]:
    document = yaml.safe_load(textwrap.dedent(text))
    assert isinstance(document, dict)
    return document


class TriggerTests(unittest.TestCase):
    def test_every_on_form(self) -> None:
        cases: tuple[tuple[str, str, frozenset[str]], ...] = (
            ("string", "on: pull_request\n", frozenset({"pull_request"})),
            ("list", "on: [push, pull_request]\n", frozenset({"push", "pull_request"})),
            ("mapping", "on:\n  pull_request:\n    types: [opened]\n  push:\n", frozenset({"pull_request", "push"})),
            ("quoted key", '"on": pull_request_target\n', frozenset({"pull_request_target"})),
            ("block list", "on:\n  - workflow_dispatch\n  - pull_request\n", frozenset({"workflow_dispatch", "pull_request"})),
        )
        for description, text, expected in cases:
            with self.subTest(description):
                self.assertEqual(triggers("w.yml", parse(text)), expected)

    def test_bare_on_is_parsed_as_boolean_true_and_still_read(self) -> None:
        document = parse("on: pull_request\n")
        self.assertIn(True, document)
        self.assertNotIn("on", document)
        self.assertEqual(triggers("w.yml", document), frozenset({"pull_request"}))

    def test_unreadable_on_is_indeterminate(self) -> None:
        cases = (
            ("missing", "name: x\n"),
            ("null", "on:\n"),
            ("empty list", "on: []\n"),
            ("list of mappings", "on: [{pull_request: {}}]\n"),
            ("number", "on: 3\n"),
        )
        for description, text in cases:
            with self.subTest(description), self.assertRaises(Indeterminate):
                triggers("w.yml", parse(text))


class CancelInProgressTests(unittest.TestCase):
    def test_truthy_values(self) -> None:
        for value in (
            True,
            "true",
            " true ",
            "${{ github.event_name == 'pull_request' }}",
            "${{ !contains(github.ref, 'main') }}",
        ):
            with self.subTest(value=value):
                self.assertTrue(cancels_in_progress({"group": "g", "cancel-in-progress": value}))

    def test_values_that_do_not_cancel(self) -> None:
        for value in (False, "false", "${{ false }}", "${{  }}", "yes", "True", 1, None, "x ${{ true }}"):
            with self.subTest(value=value):
                self.assertFalse(cancels_in_progress({"group": "g", "cancel-in-progress": value}))

    def test_concurrency_shapes_that_do_not_cancel(self) -> None:
        for concurrency in (None, "ci-${{ github.ref }}", {"group": "g"}, ["cancel-in-progress"]):
            with self.subTest(concurrency=concurrency):
                self.assertFalse(cancels_in_progress(concurrency))


class DiscoveryTests(unittest.TestCase):
    def test_reads_only_top_level_yml_and_yaml(self) -> None:
        files = {
            ".github/workflows/a.yml": "x",
            ".github/workflows/b.yaml": "x",
            ".github/workflows/notes.md": "x",
            ".github/workflows/nested/c.yml": "x",
        }
        with repo(files) as root:
            self.assertEqual([path.name for path in discover(root)], ["a.yml", "b.yaml"])

    def test_zero_workflow_files_is_indeterminate(self) -> None:
        for description, files in (
            ("no directory", {"README.md": "x"}),
            ("directory without workflows", {".github/workflows/README.md": "x"}),
        ):
            with self.subTest(description), repo(files) as root, self.assertRaises(Indeterminate):
                discover(root)

    def test_unreadable_workflow_is_indeterminate(self) -> None:
        cases = (
            ("not YAML", "on: [push\njobs: {}\n"),
            ("duplicate key", "on: push\njobs:\n  a:\n    runs-on: x\n  a:\n    runs-on: y\n"),
            ("not a mapping", "- on\n- jobs\n"),
            ("no jobs", "on: push\n"),
            ("empty jobs", "on: push\njobs: {}\n"),
            ("no trigger", "jobs:\n  a:\n    runs-on: x\n"),
        )
        for description, text in cases:
            with self.subTest(description), repo({".github/workflows/w.yml": text}) as root:
                with self.assertRaises(Indeterminate):
                    load_workflow(root / ".github/workflows/w.yml")


if __name__ == "__main__":
    unittest.main()
