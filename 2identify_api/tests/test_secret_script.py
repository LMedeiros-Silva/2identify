"""Tests for safe local secret provisioning."""

from __future__ import annotations

from pathlib import Path

from scripts.ensure_auth_secret import ensure_auth_secret


def test_ensure_auth_secret_creates_once_without_overwriting(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DATABASE_URL=postgresql://example\n", encoding="utf-8")

    assert ensure_auth_secret(env_path) is True
    first_contents = env_path.read_text(encoding="utf-8")
    assert "AUTH_TOKEN_SECRET=" in first_contents
    assert "CHANGE_ME" not in first_contents

    assert ensure_auth_secret(env_path) is False
    assert env_path.read_text(encoding="utf-8") == first_contents
