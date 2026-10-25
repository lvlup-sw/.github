"""Guards on actions/workflow-hygiene/action.yml itself.

GitHub evaluates expressions inside action METADATA, not only inside steps, and an unknown context
there makes the whole action fail to load (see the same guard in actions/ci-lanes). This test
refuses any expression in an input description, any input default outside the allowed contexts,
and an input that reaches the run script through an expression instead of env.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ACTION = Path(__file__).resolve().parents[1] / "action.yml"
EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
DEFAULT_CONTEXTS = ("github.", "env.", "runner.", "job.", "strategy.", "matrix.", "steps.", "inputs.")


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

    def test_run_script_reads_no_expression_and_pins_pyyaml(self) -> None:
        scripts = run_scripts(load_action())
        self.assertEqual(len(scripts), 1)
        self.assertIsNone(EXPRESSION.search(scripts[0]))
        self.assertIn("--managed-python --python 3.12 --with 'PyYAML==6.0.2'", scripts[0])
        self.assertIn('--root "${WORKFLOW_HYGIENE_ROOT}"', scripts[0])

    def test_the_guard_detects_the_defect_it_exists_for(self) -> None:
        self.assertIsNotNone(EXPRESSION.search('python -m workflow_hygiene --root "${{ inputs.root }}"'))


if __name__ == "__main__":
    unittest.main()
