from __future__ import annotations

import itertools
import json
import tomllib
import unittest

from ci_lanes.errors import Indeterminate
from ci_lanes.manifest import Manifest, parse_manifest
from ci_lanes.verdict import evaluate

from .consumer import MANIFEST

RESULTS = ("success", "failure", "cancelled", "skipped")


def manifest() -> Manifest:
    return parse_manifest(tomllib.loads(MANIFEST), ".github/ci-lanes.toml")


def needs(planner: str, lane_value: str | None, job: str) -> str:
    outputs: dict[str, str] = {}
    if planner == "success":
        lanes = {"build": "true", "docs": "true", "lint": "true"}
        if lane_value is not None:
            lanes["infra"] = lane_value
        outputs["lanes"] = json.dumps(lanes)
    return json.dumps({"plan": {"result": planner, "outputs": outputs}, "validate": {"result": job, "outputs": {}}})


def oracle(planner: str, lane_value: str | None, job: str) -> bool:
    """The rule, stated independently of the implementation."""
    if job == "success":
        return True
    return job == "skipped" and planner == "success" and lane_value == "false"


class VerdictGridTests(unittest.TestCase):
    def test_every_combination_matches_the_rule(self) -> None:
        for planner, lane_value, job in itertools.product(RESULTS, ("true", "false", None), RESULTS):
            if planner != "success" and lane_value is not None:
                continue  # a planner that did not succeed publishes no lanes
            with self.subTest(planner=planner, lane=lane_value, job=job):
                verdict = evaluate(manifest(), "infra-gate", needs(planner, lane_value, job))
                self.assertEqual(verdict.passed, oracle(planner, lane_value, job))

    def test_the_grid_is_not_vacuous(self) -> None:
        passing = [
            combination
            for combination in itertools.product(RESULTS, ("true", "false", None), RESULTS)
            if (combination[0] == "success" or combination[1] is None) and oracle(*combination)
        ]
        self.assertGreater(len(passing), 1)


class VerdictStructureTests(unittest.TestCase):
    def test_unexpected_and_missing_needs_fail(self) -> None:
        extra = json.dumps({
            "plan": {"result": "success", "outputs": {"lanes": '{"infra":"true"}'}},
            "validate": {"result": "success"},
            "other": {"result": "success"},
        })
        verdict = evaluate(manifest(), "infra-gate", extra)
        self.assertFalse(verdict.passed)
        self.assertIn("other", verdict.structure_problems[0])

        missing = json.dumps({"plan": {"result": "success", "outputs": {"lanes": '{"infra":"false"}'}}})
        verdict = evaluate(manifest(), "infra-gate", missing)
        self.assertFalse(verdict.passed)
        self.assertIn("validate", verdict.structure_problems[0])

    def test_indeterminate_inputs(self) -> None:
        cases: tuple[tuple[str, str, str], ...] = (
            ("unknown gate", "gate", needs("success", "false", "skipped")),
            ("empty needs", "infra-gate", ""),
            ("needs is not JSON", "infra-gate", "{"),
            ("needs is a list", "infra-gate", "[]"),
            ("needs is empty", "infra-gate", "{}"),
            ("unknown result", "infra-gate", json.dumps({"plan": {"result": "success"}, "validate": {"result": "neutral"}})),
            ("planner missing", "infra-gate", json.dumps({"validate": {"result": "success"}})),
            ("planner without lanes output", "infra-gate", json.dumps({"plan": {"result": "success", "outputs": {}}, "validate": {"result": "skipped"}})),
            ("planner lanes not JSON", "infra-gate", json.dumps({"plan": {"result": "success", "outputs": {"lanes": "{"}}, "validate": {"result": "skipped"}})),
            ("planner lane value is a boolean", "infra-gate", json.dumps({"plan": {"result": "success", "outputs": {"lanes": '{"infra": false}'}}, "validate": {"result": "skipped"}})),
        )
        for description, gate, payload in cases:
            with self.subTest(description), self.assertRaises(Indeterminate):
                evaluate(manifest(), gate, payload)


if __name__ == "__main__":
    unittest.main()
