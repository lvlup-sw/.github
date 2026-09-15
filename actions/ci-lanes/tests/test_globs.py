from __future__ import annotations

import unittest

from ci_lanes.globs import GlobError, compile_glob

MATCHES: tuple[tuple[str, str, bool], ...] = (
    ("src/**", "src/a.cs", True),
    ("src/**", "src/a/b/c.cs", True),
    ("src/**", "src", False),
    ("src/**", "srcx/a.cs", False),
    ("src/**", "lib/src/a.cs", False),
    ("**/*.md", "README.md", True),
    ("**/*.md", "docs/a/b.md", True),
    ("**/*.md", "docs/a/b.mdx", False),
    ("a/**/b.txt", "a/b.txt", True),
    ("a/**/b.txt", "a/x/y/b.txt", True),
    ("a/**/b.txt", "a/x/y/c.txt", False),
    ("Directory.*.props", "Directory.Build.props", True),
    ("Directory.*.props", "Directory.props", False),
    ("Directory.*.props", "sub/Directory.Build.props", False),
    ("global.json", "global.json", True),
    ("global.json", "globalxjson", False),
    ("scripts/?.sh", "scripts/a.sh", True),
    ("scripts/?.sh", "scripts/ab.sh", False),
    ("scripts/*.sh", "scripts/sub/a.sh", False),
    ("**", "any/path/at/all", True),
    (".github/workflows/ci.yml", ".github/workflows/ci.yml", True),
    (".github/workflows/ci.yml", ".github/workflows/ci.yaml", False),
)

REFUSED: tuple[str, ...] = (
    "",
    " src/**",
    "src/** ",
    "/src/**",
    "./src/**",
    "src/",
    "src//a",
    "src/./a",
    "src/../a",
    "src/**/**/a",
    "src/a**",
    "src/[ab].cs",
    "src/{a,b}.cs",
    "!src/**",
    "src\\a",
)


class GlobTests(unittest.TestCase):
    def test_matches(self) -> None:
        for pattern, path, expected in MATCHES:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(compile_glob(pattern).matches(path), expected)

    def test_refused(self) -> None:
        for pattern in REFUSED:
            with self.subTest(pattern=pattern), self.assertRaises(GlobError):
                compile_glob(pattern)


if __name__ == "__main__":
    unittest.main()
