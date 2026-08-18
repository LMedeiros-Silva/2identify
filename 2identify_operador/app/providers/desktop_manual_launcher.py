"""Qt adapter for opening validated local manuals in the default PDF viewer."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


class DesktopManualLauncher:
    """Delegate a local PDF to the operating system's registered viewer."""

    def open_local_pdf(self, path: Path) -> bool:
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
