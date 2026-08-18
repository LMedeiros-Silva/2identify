"""Operation concepts independent from UI, storage and transport layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from app.domain.risk_area import RiskAreaGeometry


class ManualReferenceKind(StrEnum):
    """Supported ways an operation may reference its PDF manual."""

    LOCAL_FILE = "local_file"
    REMOTE_URL = "remote_url"


@dataclass(frozen=True, slots=True)
class OperationManual:
    """Validated, storage-agnostic reference to an operation manual."""

    reference: str
    kind: ManualReferenceKind
    title: str = "Manual da operação"

    def __post_init__(self) -> None:
        normalized_reference = self.reference.strip()
        normalized_title = self.title.strip()
        if not normalized_reference:
            raise ValueError("reference do manual não pode ser vazio")
        if not normalized_title:
            raise ValueError("title do manual não pode ser vazio")
        if not isinstance(self.kind, ManualReferenceKind):
            raise ValueError("kind do manual é inválido")

        if self.kind is ManualReferenceKind.LOCAL_FILE:
            portable_path = PurePosixPath(normalized_reference.replace("\\", "/"))
            windows_path = PureWindowsPath(normalized_reference)
            if (
                portable_path.is_absolute()
                or windows_path.is_absolute()
                or bool(windows_path.drive)
            ):
                raise ValueError("reference local do manual deve ser relativa")
            if ".." in portable_path.parts:
                raise ValueError("reference local do manual não pode sair da pasta configurada")
            if portable_path.suffix.casefold() != ".pdf":
                raise ValueError("reference local do manual deve apontar para um PDF")
        else:
            parsed_url = urlsplit(normalized_reference)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                raise ValueError("URL do manual deve utilizar HTTP ou HTTPS")
            if parsed_url.username or parsed_url.password:
                raise ValueError("URL do manual não pode conter credenciais")

        object.__setattr__(self, "reference", normalized_reference)
        object.__setattr__(self, "title", normalized_title)


@dataclass(frozen=True, slots=True)
class PpeRequirement:
    """One PPE catalog item required by an industrial operation."""

    ppe_id: int
    name: str
    detection_class: str | None = None

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.ppe_id <= 0:
            raise ValueError("ppe_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name do EPI não pode ser vazio")
        detection_class = self.detection_class
        if detection_class is not None:
            detection_class = detection_class.strip().casefold()
            if not detection_class:
                raise ValueError("detection_class do EPI não pode ser vazio")
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "detection_class", detection_class)


@dataclass(frozen=True, slots=True)
class RiskAreaReference:
    """Operation association to an optionally configured camera-space risk area."""

    risk_area_id: int
    name: str
    geometry: RiskAreaGeometry | None = None
    geometry_calibrated: bool = False

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.risk_area_id <= 0:
            raise ValueError("risk_area_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name da área de risco não pode ser vazio")
        if self.geometry is not None and not isinstance(
            self.geometry,
            RiskAreaGeometry,
        ):
            raise ValueError("geometry deve ser RiskAreaGeometry ou None")
        if not isinstance(self.geometry_calibrated, bool):
            raise ValueError("geometry_calibrated deve ser booleano")
        if self.geometry_calibrated and self.geometry is None:
            raise ValueError("uma área calibrada exige geometria configurada")
        object.__setattr__(self, "name", normalized_name)


@dataclass(frozen=True, slots=True)
class Operation:
    """An industrial operation that may be offered to an operator."""

    operation_id: int
    name: str
    description: str | None = None
    required_ppe: tuple[PpeRequirement, ...] = ()
    manual: OperationManual | None = None
    risk_area: RiskAreaReference | None = None
    active: bool = True

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.operation_id <= 0:
            raise ValueError("operation_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name não pode ser vazio")
        if not isinstance(self.active, bool):
            raise ValueError("active deve ser booleano")
        if self.manual is not None and not isinstance(self.manual, OperationManual):
            raise ValueError("manual deve ser OperationManual ou None")
        if self.risk_area is not None and not isinstance(
            self.risk_area, RiskAreaReference
        ):
            raise ValueError("risk_area deve ser RiskAreaReference ou None")

        requirements = tuple(self.required_ppe)
        requirement_ids: set[int] = set()
        detection_classes: set[str] = set()
        for requirement in requirements:
            if not isinstance(requirement, PpeRequirement):
                raise ValueError("required_ppe deve conter somente PpeRequirement")
            if requirement.ppe_id in requirement_ids:
                raise ValueError(f"ppe_id obrigatório duplicado: {requirement.ppe_id}")
            requirement_ids.add(requirement.ppe_id)
            detection_class = requirement.detection_class
            if detection_class is not None:
                if detection_class in detection_classes:
                    raise ValueError(
                        f"detection_class obrigatória duplicada: {detection_class}"
                    )
                detection_classes.add(detection_class)

        description = self.description
        if description is not None:
            description = description.strip() or None

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "required_ppe", requirements)
