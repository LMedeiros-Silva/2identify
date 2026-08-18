"""Safe resolution and opening of operation manuals."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.operation import ManualReferenceKind, OperationManual


class ManualServiceError(RuntimeError):
    """Base error for failures while resolving or opening manuals."""


class ManualUnavailableError(ManualServiceError):
    """A configured manual cannot be safely accessed."""


class ManualUnsupportedError(ManualServiceError):
    """The manual reference kind is not supported by the current transport."""


class ManualOpenError(ManualServiceError):
    """The desktop environment refused to open a validated manual."""


class ManualLauncher(Protocol):
    """Desktop boundary used after a local PDF has been validated."""

    def open_local_pdf(self, path: Path) -> bool: ...


class ManualService:
    """Resolve local references below an injected root and delegate their launch."""

    def __init__(self, manuals_directory: Path, launcher: ManualLauncher) -> None:
        self._manuals_directory = manuals_directory.resolve()
        self._launcher = launcher

    def open_manual(self, manual: OperationManual) -> Path:
        """Validate and open a configured manual, returning its resolved path."""

        if manual.kind is not ManualReferenceKind.LOCAL_FILE:
            raise ManualUnsupportedError(
                "Manuais remotos aguardam a futura integração autenticada com a API."
            )

        manual_path = (self._manuals_directory / manual.reference).resolve()
        if not manual_path.is_relative_to(self._manuals_directory):
            raise ManualUnavailableError("O manual está fora da pasta configurada.")
        if not manual_path.is_file():
            raise ManualUnavailableError("O arquivo do manual não foi encontrado.")

        try:
            with manual_path.open("rb") as stream:
                signature = stream.read(5)
        except OSError as error:
            raise ManualUnavailableError("O arquivo do manual não pôde ser lido.") from error
        if signature != b"%PDF-":
            raise ManualUnavailableError("O arquivo configurado não é um PDF válido.")

        if not self._launcher.open_local_pdf(manual_path):
            raise ManualOpenError("O sistema operacional não conseguiu abrir o manual.")
        return manual_path
