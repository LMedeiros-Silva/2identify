from __future__ import annotations

import sys

from pydantic import ValidationError
from PySide6.QtWidgets import QApplication, QMessageBox

from app.api import AdminApiClient
from app.controllers import ApplicationController
from app.core.config import get_settings
from app.core.logging_config import configure_logging


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("2Identify Admin")
    application.setOrganizationName("2Identify")

    try:
        settings = get_settings()
        configure_logging(
            log_directory=settings.log_directory,
            level=settings.log_level,
        )
    except (OSError, ValidationError):
        QMessageBox.critical(
            None,
            "Configuração inválida",
            "Não foi possível iniciar o 2Identify Admin. "
            "Revise as configurações da instalação.",
        )
        return 2

    api_client = AdminApiClient(settings)
    controller = ApplicationController(application, settings, api_client)
    controller.start()
    exit_code = application.exec()
    controller.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
