"""The rules: the clean body passes, and each hostile edit yields exactly the one finding it seeds."""

from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence

from pr_body.check import Config, Report, run_check
from pr_body.errors import Indeterminate
from pr_body.markdown import headings, prose_lines

from .consumer import (
    BODY,
    CLEAN_BODY,
    FILES,
    GOLDEN_MARKER,
    GOLDEN_PATH,
    HEADINGS,
    MIRROR,
    TEMPLATE,
    TEMPLATE_TEXT,
)
from .support import mutate, repo, without


def check(
    files: Mapping[str, str],
    *,
    same_as: Sequence[str] = (),
    max_words: int = 250,
    marker: str = "",
    marker_paths: Sequence[str] = (),
    changed: Sequence[str] | None = None,
) -> Report:
    with repo(files) as root:
        config = Config(
            template=root / TEMPLATE,
            same_as=tuple(root / path for path in same_as),
            max_words=max_words,
            marker=marker,
            marker_paths=tuple(marker_paths),
        )
        return run_check(config, files[BODY], changed)


def rules(report: Report) -> list[str]:
    return [finding.rule for finding in report.violations]


def edit(old: str, new: str) -> dict[str, str]:
    return mutate(FILES, BODY, old, new)


class OrgTemplateTests(unittest.TestCase):
    def test_the_shipped_template_is_the_five_headings_in_order(self) -> None:
        found = headings(prose_lines(TEMPLATE_TEXT))
        self.assertEqual(tuple(heading.text for heading in found), HEADINGS)
        self.assertEqual({heading.level for heading in found}, {2})


class CleanBodyTests(unittest.TestCase):
    def test_clean_body_passes(self) -> None:
        report = check(FILES, same_as=[MIRROR])
        self.assertEqual(report.violations, [])
        self.assertEqual(report.template_headings, 5)
        self.assertGreater(report.words, 40)


class HeadingTests(unittest.TestCase):
    def test_missing_heading(self) -> None:
        report = check(edit("## Verification Performed\n\n- `python -m unittest` passed.\n\n", ""))
        self.assertEqual(rules(report), ["headings"])
        self.assertIn("'## Verification Performed' is missing", report.violations[0].message)

    def test_sixth_heading(self) -> None:
        report = check(edit("## Post-Merge Operations", "## Test Plan\n\nRan it.\n\n## Post-Merge Operations"))
        self.assertEqual(rules(report), ["headings"])
        self.assertIn("'## Test Plan' is not a template heading", report.violations[0].message)

    def test_subheading_is_a_sixth_heading(self) -> None:
        report = check(edit("- **Example**", "### Details\n\n- **Example**"))
        self.assertEqual(rules(report), ["headings"])

    def test_level_one_heading_is_a_sixth_heading(self) -> None:
        report = check(edit("## Background", "# Title\n\n## Background"))
        self.assertEqual(rules(report), ["headings"])

    def test_repeated_heading(self) -> None:
        report = check(edit("None.\n", "None.\n\n## Changes\n\nMore.\n"))
        self.assertEqual(rules(report), ["headings"])
        self.assertIn("appears twice", report.violations[0].message)

    def test_out_of_order(self) -> None:
        swapped = edit("## Verification Performed", "## Post-Merge Operations TEMP")
        swapped = mutate(swapped, BODY, "## Post-Merge Operations\n", "## Verification Performed\n")
        swapped = mutate(swapped, BODY, "## Post-Merge Operations TEMP", "## Post-Merge Operations")
        report = check(swapped)
        self.assertEqual(rules(report), ["headings"])
        self.assertIn("out of order", report.violations[0].message)


class ContentTests(unittest.TestCase):
    def test_empty_section(self) -> None:
        report = check(edit("None.\n", ""))
        self.assertEqual(rules(report), ["empty-section"])
        self.assertIn("'Post-Merge Operations' is empty; write None.", report.violations[0].message)

    def test_section_holding_only_the_hint_is_empty_and_the_hint_is_refused(self) -> None:
        report = check(edit("None.\n", "<!-- Steps a human must do after merge. -->\n"))
        self.assertEqual(sorted(rules(report)), ["empty-section", "html-comment"])

    def test_leftover_comment(self) -> None:
        report = check(edit("Closes #12\n", "Closes #12\n<!-- Why this change exists. -->\n"))
        self.assertEqual(rules(report), ["html-comment"])

    def test_generator_footers(self) -> None:
        for footer in (
            "\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)",
            "Made with Cursor",
            "_generated with a tool_",
        ):
            with self.subTest(footer=footer):
                self.assertEqual(rules(check(edit("None.\n", f"None.\n\n{footer}\n"))), ["footer"])

    def test_generated_with_inside_a_sentence_is_prose(self) -> None:
        self.assertEqual(rules(check(edit("None.\n", "None. The file is generated with make.\n"))), [])

    def test_word_cap(self) -> None:
        base = check(FILES).words
        padding = " ".join(["word"] * (251 - base))
        at_cap = edit("None.\n", f"None. {padding}\n")
        self.assertEqual(check(at_cap).words, 251)
        self.assertEqual(rules(check(at_cap)), ["word-cap"])
        self.assertEqual(rules(check(at_cap, max_words=251)), [])
        self.assertEqual(rules(check(at_cap, max_words=0)), [])


class SameAsTests(unittest.TestCase):
    def test_a_drifted_mirror(self) -> None:
        drifted = mutate(FILES, MIRROR, "## Changes", "## Change Summary")
        report = check(drifted, same_as=[MIRROR])
        self.assertEqual(rules(report), ["same-as"])
        self.assertIn("differs from", report.violations[0].message)

    def test_a_missing_mirror(self) -> None:
        report = check(without(FILES, MIRROR), same_as=[MIRROR])
        self.assertEqual(rules(report), ["same-as"])
        self.assertIn("does not exist", report.violations[0].message)


class MarkerTests(unittest.TestCase):
    CHANGED = ("src/app.ts", f"{GOLDEN_PATH}/rehydrate.json")

    def marker(self, files: Mapping[str, str], changed: Sequence[str]) -> Report:
        return check(files, marker=GOLDEN_MARKER, marker_paths=[GOLDEN_PATH + "/"], changed=changed)

    def test_marker_needed_and_missing(self) -> None:
        report = self.marker(FILES, self.CHANGED)
        self.assertEqual(rules(report), ["marker"])
        self.assertIn(f"{GOLDEN_PATH}/rehydrate.json", report.violations[0].message)
        self.assertEqual(report.marker_paths_touched, 1)

    def test_marker_with_a_reason_passes(self) -> None:
        files = edit("Closes #12\n", f"Closes #12\n\n{GOLDEN_MARKER} the event shape changed.\n")
        self.assertEqual(rules(self.marker(files, self.CHANGED)), [])

    def test_a_bare_marker_fails(self) -> None:
        files = edit("Closes #12\n", f"Closes #12\n\n{GOLDEN_MARKER}\n")
        self.assertEqual(rules(self.marker(files, self.CHANGED)), ["marker"])

    def test_a_marker_inside_a_comment_does_not_count(self) -> None:
        files = edit("Closes #12\n", f"Closes #12\n<!-- {GOLDEN_MARKER} hidden reason -->\n")
        self.assertEqual(sorted(rules(self.marker(files, self.CHANGED))), ["html-comment", "marker"])

    def test_no_marker_path_changed(self) -> None:
        report = self.marker(FILES, ("src/app.ts", f"{GOLDEN_PATH}-notes/readme.md"))
        self.assertEqual(rules(report), [])
        self.assertEqual(report.marker_paths_touched, 0)


class IndeterminateTemplateTests(unittest.TestCase):
    def test_a_template_with_no_heading(self) -> None:
        with self.assertRaisesRegex(Indeterminate, "has no heading"):
            check(mutate(FILES, TEMPLATE, TEMPLATE_TEXT, "Write a good body.\n"))

    def test_a_template_that_repeats_a_heading(self) -> None:
        with self.assertRaisesRegex(Indeterminate, "repeats a heading"):
            check({**FILES, TEMPLATE: TEMPLATE_TEXT + "\n## Changes\n"})

    def test_a_missing_template(self) -> None:
        with repo(FILES) as root, self.assertRaisesRegex(Indeterminate, "cannot read the template"):
            run_check(Config(template=root / "absent.md"), CLEAN_BODY)


if __name__ == "__main__":
    unittest.main()
