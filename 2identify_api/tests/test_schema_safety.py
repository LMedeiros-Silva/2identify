"""Regression guards against accidental ownership or schema mutation."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_application_has_no_create_all_call() -> None:
    application_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "app").rglob("*.py")
    )

    assert ".create_all(" not in application_source
    assert ".drop_all(" not in application_source


def test_environment_file_is_ignored() -> None:
    ignored_entries = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignored_entries
