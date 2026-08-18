"""In-memory operation source exclusively for development and automated tests."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.operation import (
    ManualReferenceKind,
    Operation,
    OperationManual,
    PpeRequirement,
    RiskAreaReference,
)
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry

_SAFETY_BOOTS = PpeRequirement(
    ppe_id=1,
    name="Botas de segurança",
    detection_class="bota",
)
_SAFETY_HELMET = PpeRequirement(
    ppe_id=2,
    name="Capacete de segurança",
    detection_class="capacete",
)
_PROTECTIVE_GLOVES = PpeRequirement(
    ppe_id=3,
    name="Luvas de proteção",
    detection_class="luva",
)
_PROTECTIVE_SLEEVES = PpeRequirement(
    ppe_id=4,
    name="Mangotes",
    detection_class="mangote",
)

def _geometry(*vertices: tuple[float, float]) -> RiskAreaGeometry:
    return RiskAreaGeometry(tuple(NormalizedPoint(x, y) for x, y in vertices))


_PRODUCTION_LINE_A = RiskAreaReference(
    risk_area_id=1,
    name="Linha de Produção A",
    geometry=_geometry((0.08, 0.72), (0.34, 0.38), (0.76, 0.38), (0.94, 0.90)),
)
_WELDING_CELL = RiskAreaReference(
    risk_area_id=2,
    name="Célula de soldagem",
    geometry=_geometry((0.18, 0.30), (0.82, 0.30), (0.88, 0.88), (0.12, 0.88)),
)
_ELECTRICAL_ROOM = RiskAreaReference(
    risk_area_id=3,
    name="Sala elétrica",
    geometry=_geometry((0.46, 0.22), (0.91, 0.36), (0.86, 0.91), (0.42, 0.82)),
)
_RECEIVING_DOCK = RiskAreaReference(
    risk_area_id=4,
    name="Doca de recebimento",
    geometry=_geometry((0.05, 0.58), (0.42, 0.35), (0.93, 0.62), (0.84, 0.94)),
)

_DEVELOPMENT_OPERATIONS = (
    Operation(
        operation_id=1,
        name="Manutenção industrial",
        description="Inspeção e manutenção preventiva de equipamentos industriais.",
        required_ppe=(_SAFETY_HELMET, _PROTECTIVE_SLEEVES, _SAFETY_BOOTS),
        manual=OperationManual(
            reference="development/manutencao-industrial-demo.pdf",
            kind=ManualReferenceKind.LOCAL_FILE,
            title="Manual demonstrativo - Manutenção industrial",
        ),
        risk_area=_PRODUCTION_LINE_A,
    ),
    Operation(
        operation_id=2,
        name="Soldagem",
        description="Atividade de união e reparo de componentes metálicos.",
        required_ppe=(
            _SAFETY_HELMET,
            _PROTECTIVE_GLOVES,
            _SAFETY_BOOTS,
            _PROTECTIVE_SLEEVES,
        ),
        risk_area=_WELDING_CELL,
    ),
    Operation(
        operation_id=3,
        name="Manutenção elétrica",
        description="Intervenção controlada em instalações e equipamentos elétricos.",
        required_ppe=(_SAFETY_HELMET, _PROTECTIVE_GLOVES, _SAFETY_BOOTS),
        risk_area=_ELECTRICAL_ROOM,
    ),
    Operation(
        operation_id=4,
        name="Carga e descarga",
        description="Movimentação segura de materiais na área operacional.",
        required_ppe=(_SAFETY_HELMET, _PROTECTIVE_GLOVES, _SAFETY_BOOTS),
        risk_area=_RECEIVING_DOCK,
    ),
)


class MockOperationProvider:
    """Return deterministic local data without pretending to be an API source."""

    def __init__(self, operations: Sequence[Operation] | None = None) -> None:
        self._operations = (
            tuple(operations) if operations is not None else _DEVELOPMENT_OPERATIONS
        )

    def list_operations(self) -> tuple[Operation, ...]:
        return self._operations
