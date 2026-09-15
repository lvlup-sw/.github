"""Shared helpers: throwaway git repositories and a controlled GitHub Actions environment."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

_GIT = [
    "git",
    "-c", "user.name=ci-lanes-test",
    "-c", "user.email=ci-lanes@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "init.defaultBranch=main",
]
_ACTIONS_VARIABLES = frozenset({
    "GITHUB_ACTIONS", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GITHUB_EVENT_NAME",
    "CI_LANES_BASE_SHA", "CI_LANES_HEAD_SHA", "CI_LANES_NEEDS",
})


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run([*_GIT, "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def write_files(root: Path, files: Mapping[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


@contextmanager
def git_repo(files: Mapping[str, str]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="ci-lanes-") as directory:
        repo = Path(directory)
        git(repo, "init", "-q")
        write_files(repo, files)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixture")
        yield repo


def commit(repo: Path, files: Mapping[str, str], message: str = "change") -> str:
    write_files(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def mutate(files: Mapping[str, str], path: str, old: str, new: str) -> dict[str, str]:
    """Return a copy of ``files`` with one edit, refusing an edit that would change nothing."""
    text = files[path]
    if old not in text:
        raise AssertionError(f"hostile edit is vacuous: {old!r} is not in {path}")
    changed = dict(files)
    changed[path] = text.replace(old, new, 1)
    return changed


@contextmanager
def actions_environment(**overrides: str) -> Iterator[None]:
    environment = {key: value for key, value in os.environ.items() if key not in _ACTIONS_VARIABLES}
    environment.update(overrides)
    with mock.patch.dict(os.environ, environment, clear=True):
        yield


def read_outputs(path: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        outputs[name] = value
    return outputs
