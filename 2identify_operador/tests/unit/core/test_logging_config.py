import json
import logging

from app.core.config import AppSettings
from app.core.constants import LOG_FILE_NAME
from app.core.logging_config import configure_logging


def test_structured_logging_writes_context_to_file(tmp_path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_directory=tmp_path,
        log_format="json",
    )
    log_path = configure_logging(settings)

    logging.getLogger("test.operator").info(
        "camera_connected",
        extra={"camera_id": "CAM-01"},
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert log_path.name == LOG_FILE_NAME
    assert payload["event"] == "camera_connected"
    assert payload["context"]["camera_id"] == "CAM-01"

