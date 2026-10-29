"""Shared helpers: throwaway repository trees and a controlled GitHub Actions environment."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

_ACTIONS_VARIABLES = frozenset({"GITHUB_ACTIONS", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"})


def write_files(root: Path, files: Mapping[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


@contextmanager
def repo(files: Mapping[str, str]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="pr-body-") as directory:
        root = Path(directory)
        write_files(root, files)
        yield root


def mutate(files: Mapping[str, str], path: str, old: str, new: str) -> dict[str, str]:
    """Return a copy of ``files`` with one edit, refusing an edit that would change nothing."""
    text = files[path]
    if old not in text:
        raise AssertionError(f"hostile edit is vacuous: {old!r} is not in {path}")
    changed = dict(files)
    changed[path] = text.replace(old, new, 1)
    return changed


def without(files: Mapping[str, str], path: str) -> dict[str, str]:
    if path not in files:
        raise AssertionError(f"removal is vacuous: {path} is not in the fixture")
    return {key: value for key, value in files.items() if key != path}


@contextmanager
def actions_environment(**overrides: str) -> Iterator[None]:
    environment = {key: value for key, value in os.environ.items() if key not in _ACTIONS_VARIABLES}
    environment.update(overrides)
    with mock.patch.dict(os.environ, environment, clear=True):
        yield
