from __future__ import annotations

import tomllib
import unittest

from ci_lanes.errors import Indeterminate
from ci_lanes.manifest import Manifest, parse_manifest

from .consumer import MANIFEST
from .support import mutate


def parse(text: str) -> Manifest:
    return parse_manifest(tomllib.loads(text), ".github/ci-lanes.toml")


# (description, old text, new text, fragment of the INDETERMINATE message)
REFUSALS: tuple[tuple[str, str, str, str], ...] = (
    ("unknown top-level key", "schema_version = 1", "schema_version = 1\nlane = {}", "unknown key(s) lane"),
    ("boolean schema version", "schema_version = 1", "schema_version = true", "schema_version must be 1"),
    ("wrong schema version", "schema_version = 1", "schema_version = 2", "schema_version must be 1"),
    ("unknown lane key", 'paths = ["docs/**"]', 'paths = ["docs/**"]\npath = ["x"]', "unknown key(s) path"),
    ("lane key with a hyphen", "[lanes.docs]", "[lanes.docs-site]", "a lane key must match"),
    ("empty paths", 'paths = ["docs/**"]', "paths = []", "must be a non-empty array"),
    ("duplicate path", 'paths = ["docs/**"]', 'paths = ["docs/**", "docs/**"]', "twice"),
    ("unsupported glob", 'paths = ["docs/**"]', 'paths = ["docs/[ab]"]', "unsupported character"),
    ("workflow outside workflows dir", 'workflows = ["docs.yml"]', 'workflows = ["sub/docs.yml"]', "must be a file name"),
    ("exemption without a reason", 'paths = ["docs/**"]', 'paths = ["docs/**"]\nexempt_paths = { "README.md" = " " }', "must state a reason"),
    ("gate names an unknown lane", 'jobs = { validate = "infra" }', 'jobs = { validate = "infrastructure" }', "must name a declared lane"),
    ("gate lane does not list the workflow", 'jobs = { validate = "infra" }', 'jobs = { validate = "docs" }', "does not list matrix.yml"),
    ("gate covers the planner", 'jobs = { validate = "infra" }', 'jobs = { plan = "infra" }', "cannot be gated"),
    ("gate is the planner", "[gates.infra-gate]", "[gates.plan]", "cannot be the planner job"),
    ("unknown gate key", 'workflow = "matrix.yml"', 'workflow = "matrix.yml"\nneeds = []', "unknown key(s) needs"),
    ("fixture names an unknown lane", "docs = true }", "docs = true, site = true }", "'site' is not a declared lane"),
    ("fixture expectation is not a boolean", "docs = true }", 'docs = "true" }', "must be true or false"),
    ("fixture path is absolute", 'files = ["docs/readme.md"]', 'files = ["/docs/readme.md"]', "not repository-relative"),
)


class ManifestTests(unittest.TestCase):
    def test_consumer_manifest_parses(self) -> None:
        manifest = parse(MANIFEST)
        self.assertEqual(sorted(manifest.lanes), ["build", "docs", "infra", "lint"])
        self.assertEqual(manifest.planner_job, "plan")
        self.assertEqual(dict(manifest.gates["infra-gate"].jobs), {"validate": "infra"})
        self.assertTrue(manifest.lanes["build"].matches(".github/workflows/ci.yml"))
        self.assertFalse(manifest.lanes["docs"].matches(".github/workflows/ci.yml"))

    def test_refusals(self) -> None:
        files = {"manifest": MANIFEST}
        for description, old, new, fragment in REFUSALS:
            with self.subTest(description):
                text = mutate(files, "manifest", old, new)["manifest"]
                with self.assertRaises(Indeterminate) as caught:
                    parse(text)
                self.assertIn(fragment, str(caught.exception))

    def test_job_covered_by_two_gates_is_refused(self) -> None:
        text = MANIFEST + '\n[gates.second-gate]\nworkflow = "matrix.yml"\njobs = { validate = "infra" }\n'
        with self.assertRaises(Indeterminate) as caught:
            parse(text)
        self.assertIn("covered by both gate", str(caught.exception))

    def test_duplicate_fixture_name_is_refused(self) -> None:
        text = MANIFEST + '\n[[fixtures]]\nname = "docs only"\nfiles = ["src/app.cs"]\nexpect = { build = true }\n'
        with self.assertRaises(Indeterminate) as caught:
            parse(text)
        self.assertIn("used twice", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
