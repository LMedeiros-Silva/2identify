"""Replaceable data-source implementations used by application services."""

from app.providers.desktop_manual_launcher import DesktopManualLauncher
from app.providers.mock_operation_provider import MockOperationProvider

__all__ = ["DesktopManualLauncher", "MockOperationProvider"]
