"""Shared isolated test configuration."""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
)
os.environ["APP_ENV"] = "testing"
os.environ["AUTH_TOKEN_SECRET"] = "test-only-secret-with-at-least-32-bytes"
