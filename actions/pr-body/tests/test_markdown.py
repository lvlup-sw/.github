"""The parser: fences and comments hide structure, and words are counted only in visible prose."""

from __future__ import annotations

import unittest

from pr_body.markdown import comment_lines, headings, prose_lines, sections, word_count


class MarkdownTests(unittest.TestCase):
    def test_a_fenced_heading_is_not_a_heading(self) -> None:
        text = "## One\n\n```\n## Two\n```\n\n~~~~\n## Three\n~~~\n~~~~\n## Four\n"
        self.assertEqual([heading.text for heading in headings(prose_lines(text))], ["One", "Four"])

    def test_a_heading_inside_a_comment_is_not_a_heading(self) -> None:
        text = "## One\n<!--\n## Two\n-->\n## Three\n"
        self.assertEqual([heading.text for heading in headings(prose_lines(text))], ["One", "Three"])

    def test_closing_hashes_and_case_are_normalised(self) -> None:
        found = headings(prose_lines("##   Design Decisions ##\n"))
        self.assertEqual(found[0].text, "Design Decisions")
        self.assertEqual(found[0].level, 2)
        self.assertEqual(found[0].key, "design decisions")

    def test_a_hash_with_no_space_is_text(self) -> None:
        self.assertEqual(headings(prose_lines("#123 is the issue\n")), [])

    def test_comment_lines_ignore_inline_code_and_fences(self) -> None:
        text = "Use `<!--` in prose.\n```\n<!-- fenced -->\n```\nA <!-- real --> one.\n"
        self.assertEqual([line.number for line in comment_lines(prose_lines(text))], [5])

    def test_word_count_skips_headings_fences_and_comments(self) -> None:
        text = "## Heading words\n\nOne two, three.\n<!-- four\nfive -->\n```\nsix seven\n```\n- eight -- `nine`\n"
        self.assertEqual(word_count(prose_lines(text)), 5)

    def test_an_empty_body_has_no_structure(self) -> None:
        self.assertEqual((headings(prose_lines("")), word_count(prose_lines(""))), ([], 0))

    def test_a_section_holding_only_a_comment_is_empty(self) -> None:
        text = "## One\n<!-- hint\nacross lines -->\n\n## Two\nText.\n"
        found = sections(prose_lines(text))
        self.assertEqual([(section.heading.text, section.is_empty) for section in found], [("One", True), ("Two", False)])


if __name__ == "__main__":
    unittest.main()
