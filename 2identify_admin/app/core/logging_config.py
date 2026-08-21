from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _SensitiveDataFilter(logging.Filter):
    """Impede a inclusão acidental de segredos em campos estruturados."""

    _blocked_fragments = ("password", "senha", "token", "authorization", "secret")

    def filter(self, record: logging.LogRecord) -> bool:
        for key in tuple(record.__dict__):
            if any(fragment in key.lower() for fragment in self._blocked_fragments):
                record.__dict__[key] = "[REDACTED]"
        return True


def configure_logging(*, log_directory: Path, level: str) -> None:
    log_directory.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    sensitive_filter = _SensitiveDataFilter()

    file_handler = RotatingFileHandler(
        log_directory / "2identify_admin.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
