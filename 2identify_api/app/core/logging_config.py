"""Structured logging without credentials or database URLs."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any

_STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)
_SENSITIVE_FIELD_FRAGMENTS = ("password", "secret", "token", "database_url")


class JsonFormatter(logging.Formatter):
    """Emit compact JSON events suitable for local diagnostics and collection."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            if any(fragment in key.casefold() for fragment in _SENSITIVE_FIELD_FRAGMENTS):
                payload[key] = "[REDACTED]"
            elif isinstance(value, str | int | float | bool) or value is None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Configure process-wide structured application logs once per app factory call."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": sys.stdout,
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": level, "propagate": False},
            },
        }
    )

