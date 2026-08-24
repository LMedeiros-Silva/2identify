"""Tests for safe shared catalog-token provisioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ensure_operator_catalog_token import ensure_operator_catalog_token


def _setting(path: Path) -> str:
    prefix = "OPERATOR_CATALOG_TOKEN="
    return next(
        line.removeprefix(prefix)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )


def test_catalog_token_is_generated_once_and_synchronized(tmp_path: Path) -> None:
    api_env = tmp_path / "api.env"
    operator_env = tmp_path / "operator.env"
    api_env.write_text("DATABASE_URL=example\n", encoding="utf-8")
    operator_env.write_text("API_URL=example\n", encoding="utf-8")

    assert ensure_operator_catalog_token(api_env, operator_env) == (True, True)
    assert _setting(api_env) == _setting(operator_env)
    assert len(_setting(api_env).encode("utf-8")) >= 32
    assert ensure_operator_catalog_token(api_env, operator_env) == (False, False)


def test_catalog_token_does_not_overwrite_conflicting_valid_values(tmp_path: Path) -> None:
    api_env = tmp_path / "api.env"
    operator_env = tmp_path / "operator.env"
    api_env.write_text("OPERATOR_CATALOG_TOKEN=" + ("a" * 40) + "\n", encoding="utf-8")
    operator_env.write_text(
        "OPERATOR_CATALOG_TOKEN=" + ("b" * 40) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="diferentes"):
        ensure_operator_catalog_token(api_env, operator_env)

    assert _setting(api_env) == "a" * 40
    assert _setting(operator_env) == "b" * 40
