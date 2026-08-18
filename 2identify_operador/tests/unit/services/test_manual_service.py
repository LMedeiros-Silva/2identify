from pathlib import Path

import pytest

from app.domain.operation import ManualReferenceKind, OperationManual
from app.services.manual_service import (
    ManualOpenError,
    ManualService,
    ManualUnavailableError,
    ManualUnsupportedError,
)


class RecordingLauncher:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.received: Path | None = None

    def open_local_pdf(self, path: Path) -> bool:
        self.received = path
        return self.accepted


def _manual(reference: str = "operation.pdf") -> OperationManual:
    return OperationManual(reference, ManualReferenceKind.LOCAL_FILE)


def test_manual_service_opens_a_valid_pdf_below_configured_root(tmp_path: Path) -> None:
    manual_path = tmp_path / "operation.pdf"
    manual_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    launcher = RecordingLauncher()

    opened_path = ManualService(tmp_path, launcher).open_manual(_manual())

    assert opened_path == manual_path.resolve()
    assert launcher.received == manual_path.resolve()


def test_manual_service_rejects_missing_or_invalid_pdf(tmp_path: Path) -> None:
    service = ManualService(tmp_path, RecordingLauncher())

    with pytest.raises(ManualUnavailableError, match="não foi encontrado"):
        service.open_manual(_manual())

    (tmp_path / "operation.pdf").write_bytes(b"arquivo incorreto")
    with pytest.raises(ManualUnavailableError, match="não é um PDF"):
        service.open_manual(_manual())


def test_manual_service_normalizes_desktop_launch_failure(tmp_path: Path) -> None:
    (tmp_path / "operation.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    with pytest.raises(ManualOpenError):
        ManualService(tmp_path, RecordingLauncher(accepted=False)).open_manual(_manual())


def test_manual_service_defers_remote_manuals_to_authenticated_api(tmp_path: Path) -> None:
    remote = OperationManual(
        "https://api.example.test/operations/7/manual",
        ManualReferenceKind.REMOTE_URL,
    )

    with pytest.raises(ManualUnsupportedError, match="API"):
        ManualService(tmp_path, RecordingLauncher()).open_manual(remote)
