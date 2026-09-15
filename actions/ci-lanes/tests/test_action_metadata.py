"""Guards on actions/ci-lanes/action.yml itself.

GitHub evaluates expressions inside action METADATA, not only inside steps. A literal
`${{ toJSON(needs) }}` in an input description made the whole action fail to load on the first
canary run ("Unrecognized named-value: 'needs'"). actionlint does not report it, and a local run of
the step script cannot see it, so this test refuses the class: no expression in any input or
output description, and no expression in an input default outside the contexts GitHub allows
there.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ACTION = Path(__file__).resolve().parents[1] / "action.yml"
EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
# Contexts GitHub makes available to an input default in action metadata.
DEFAULT_CONTEXTS = ("github.", "env.", "runner.", "job.", "strategy.", "matrix.", "steps.", "inputs.")


def load_action() -> dict[str, object]:
    document = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "action.yml must be a mapping"
    return {str(key): value for key, value in document.items()}


def section(document: dict[str, object], name: str) -> dict[str, dict[str, object]]:
    value = document.get(name) or {}
    assert isinstance(value, dict), f"{name} must be a mapping"
    return {str(key): dict(entry) for key, entry in value.items() if isinstance(entry, dict)}


class ActionMetadataTests(unittest.TestCase):
    def test_descriptions_carry_no_expression(self) -> None:
        document = load_action()
        for kind in ("inputs", "outputs"):
            for name, entry in section(document, kind).items():
                with self.subTest(kind=kind, name=name):
                    description = str(entry.get("description", ""))
                    self.assertIsNone(EXPRESSION.search(description), f"{kind}.{name}.description holds an expression")

    def test_input_defaults_use_only_allowed_contexts(self) -> None:
        for name, entry in section(load_action(), "inputs").items():
            for match in EXPRESSION.finditer(str(entry.get("default", ""))):
                with self.subTest(name=name, expression=match.group(0)):
                    self.assertTrue(match.group("body").strip().startswith(DEFAULT_CONTEXTS))

    def test_the_guard_detects_the_defect_it_exists_for(self) -> None:
        self.assertIsNotNone(EXPRESSION.search("mode=verdict only: pass exactly ${{ toJSON(needs) }}."))


if __name__ == "__main__":
    unittest.main()
