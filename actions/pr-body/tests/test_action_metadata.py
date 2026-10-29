"""Guards on actions/pr-body/action.yml itself.

GitHub evaluates expressions inside action METADATA, not only inside steps, and an unknown context
there makes the whole action fail to load (see the same guard in actions/ci-lanes). This test
refuses any expression in an input description, any input default outside the allowed contexts,
and an input that reaches the run script through an expression instead of env. It also proves that
the default template path in the script resolves to the org template this repository ships.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from .consumer import ORG_TEMPLATE

ACTION_DIR = Path(__file__).resolve().parents[1]
ACTION = ACTION_DIR / "action.yml"
EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
DEFAULT_CONTEXTS = ("github.", "env.", "runner.", "job.", "strategy.", "matrix.", "steps.", "inputs.")
DEFAULT_TEMPLATE = re.compile(r'template="\$\{PR_BODY_TEMPLATE:-\$\{PR_BODY_PACKAGE\}/(?P<path>[^}"]+)\}"')


def load_action() -> dict[str, object]:
    document = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "action.yml must be a mapping"
    return {str(key): value for key, value in document.items()}


def inputs(document: dict[str, object]) -> dict[str, dict[str, object]]:
    value = document.get("inputs") or {}
    assert isinstance(value, dict), "inputs must be a mapping"
    return {str(key): dict(entry) for key, entry in value.items() if isinstance(entry, dict)}


def run_scripts(document: dict[str, object]) -> list[str]:
    runs = document.get("runs")
    assert isinstance(runs, dict)
    steps = runs.get("steps")
    assert isinstance(steps, list)
    return [str(step["run"]) for step in steps if isinstance(step, dict) and "run" in step]


class ActionMetadataTests(unittest.TestCase):
    def test_descriptions_carry_no_expression(self) -> None:
        document = load_action()
        self.assertIsNone(EXPRESSION.search(str(document.get("description", ""))))
        for name, entry in inputs(document).items():
            with self.subTest(name=name):
                self.assertIsNone(EXPRESSION.search(str(entry.get("description", ""))))

    def test_input_defaults_use_only_allowed_contexts(self) -> None:
        for name, entry in inputs(load_action()).items():
            for match in EXPRESSION.finditer(str(entry.get("default", ""))):
                with self.subTest(name=name, expression=match.group(0)):
                    self.assertTrue(match.group("body").strip().startswith(DEFAULT_CONTEXTS))

    def test_run_script_reads_no_expression_and_needs_no_package(self) -> None:
        scripts = run_scripts(load_action())
        self.assertEqual(len(scripts), 1)
        self.assertIsNone(EXPRESSION.search(scripts[0]))
        self.assertNotIn("--with", scripts[0])
        self.assertIn('event="${PR_BODY_EVENT_FILE:-${GITHUB_EVENT_PATH}}"', scripts[0])
        self.assertIn('--event-file="${event}"', scripts[0])

    def test_every_input_reaches_the_script(self) -> None:
        script = run_scripts(load_action())[0]
        for name in inputs(load_action()):
            with self.subTest(name=name):
                variable = "PR_BODY_ROOT" if name == "working-directory" else "PR_BODY_" + name.upper().replace("-", "_")
                self.assertIn("${" + variable, script)

    def test_default_template_is_the_shipped_org_template(self) -> None:
        match = DEFAULT_TEMPLATE.search(run_scripts(load_action())[0])
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual((ACTION_DIR / match.group("path")).resolve(), ORG_TEMPLATE)
        self.assertTrue(ORG_TEMPLATE.is_file())

    def test_the_guard_detects_the_defect_it_exists_for(self) -> None:
        self.assertIsNotNone(EXPRESSION.search('python -m pr_body --template "${{ inputs.template }}"'))


if __name__ == "__main__":
    unittest.main()
