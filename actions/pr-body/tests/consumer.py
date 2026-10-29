"""The shipped org template, and a body that follows every rule.

Every hostile test starts from these bytes and makes one edit, so a green baseline is what makes
each refusal meaningful. The body covers each shape the rules must accept: a heading in other
case, a fenced example that holds a heading, an HTML comment and a footer, a bullet list, and
``None.`` under an empty heading.
"""

from __future__ import annotations

from pathlib import Path

ORG_TEMPLATE = Path(__file__).resolve().parents[3] / ".github" / "PULL_REQUEST_TEMPLATE.md"
TEMPLATE_TEXT = ORG_TEMPLATE.read_text(encoding="utf-8")

TEMPLATE = ".github/PULL_REQUEST_TEMPLATE.md"
MIRROR = ".exarchos/pr-template.md"
BODY = "body.md"

HEADINGS = ("Background", "Design Decisions", "Changes", "Verification Performed", "Post-Merge Operations")

CLEAN_BODY = """\
## Background

The PR body check only looked for the five headings.
It did not check their order or the word cap.

Closes #12

## design decisions

- Keep the check in the standard library, like the other actions.

## Changes

- **Checker**: refuses an extra heading, a hint, a footer and a long body.
- **Example**: a fenced block is not structure.

```markdown
## Summary
<!-- a hint inside a fence -->
Generated with a tool
```

## Verification Performed

- `python -m unittest` passed.

## Post-Merge Operations

None.
"""

GOLDEN_MARKER = "GOLDEN-FIXTURE-UPDATE:"
GOLDEN_PATH = "tests/fixtures/load-bearing"

FILES: dict[str, str] = {
    TEMPLATE: TEMPLATE_TEXT,
    MIRROR: TEMPLATE_TEXT,
    BODY: CLEAN_BODY,
}
