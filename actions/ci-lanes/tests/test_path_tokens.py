from __future__ import annotations

import unittest

from ci_lanes.check import path_tokens

TRACKED = frozenset({"README.md", "scripts/build.sh", "sub/app.cs", "sub/deep/tool.sh", "release/notes.md"})
DIRECTORIES = frozenset({"scripts", "sub", "sub/deep", "release"})

# (text, base, expected names)
CASES: tuple[tuple[str, str | None, tuple[str, ...]], ...] = (
    ("bash scripts/build.sh", "", ("scripts/build.sh",)),
    ("bash ./scripts/build.sh", "", ("scripts/build.sh",)),
    ("cat README.md", "", ("README.md",)),
    ("cat README.md", "sub", ()),
    ("cat app.cs deep/tool.sh", "sub", ("sub/app.cs", "sub/deep/tool.sh")),
    ("cat ../README.md", "sub", ("README.md",)),
    ("ls deep/", "sub", ("sub/deep",)),
    ("echo prepare the release", "", ()),
    ("ls release/", "", ("release",)),
    ("cat ../../outside.txt", "sub", ()),
    ("cat /etc/passwd README.md", "", ("README.md",)),
    ("bash ${{ matrix.script }} scripts/*.sh", "", ()),
    ("curl https://example.invalid/scripts/build.sh", "", ()),
    ("--project=sub/app.cs", "", ("sub/app.cs",)),
    ("cat app.cs README.md", None, ()),
)


class PathTokenTests(unittest.TestCase):
    def test_cases(self) -> None:
        for text, base, expected in CASES:
            with self.subTest(text=text, base=base):
                self.assertEqual(tuple(path_tokens(text, base, TRACKED, DIRECTORIES)), expected)


if __name__ == "__main__":
    unittest.main()
