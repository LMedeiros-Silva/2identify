"""Transactional persistence for operations, required PPE and risk areas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.models import (
    CATALOG_CAMERAS,
    CATALOG_EPIS,
    CATALOG_SECTORS,
    OPERATION_EPIS,
    OPERATIONS,
    RISK_AREAS,
)


class OperationConfigurationNotFoundError(RuntimeError):
    pass


class OperationConfigurationConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EpiRecord:
    id: int
    name: str
    code: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class CameraRecord:
    id: int
    name: str
    description: str | None
    stream_source: str


@dataclass(frozen=True, slots=True)
class SectorRecord:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class RiskAreaRecord:
    id: int
    camera_id: int
    camera_name: str
    name: str
    geometry: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationRecord:
    id: int
    name: str
    description: str | None
    required_ppe: tuple[EpiRecord, ...]
    risk_area: RiskAreaRecord
    active: bool
    created_at: datetime
    updated_at: datetime


class OperationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def catalog(
        self,
    ) -> tuple[tuple[CameraRecord, ...], tuple[EpiRecord, ...], tuple[SectorRecord, ...]]:
        camera_rows = self._session.execute(
            select(
                CATALOG_CAMERAS.c.id,
                CATALOG_CAMERAS.c.nome,
                CATALOG_CAMERAS.c.descricao,
                CATALOG_CAMERAS.c.endereco,
            )
            .where(CATALOG_CAMERAS.c.ativa.is_(True))
            .order_by(CATALOG_CAMERAS.c.nome, CATALOG_CAMERAS.c.id)
        ).all()
        epi_rows = self._session.execute(
            select(
                CATALOG_EPIS.c.id,
                CATALOG_EPIS.c.nome,
                CATALOG_EPIS.c.codigo,
                CATALOG_EPIS.c.descricao,
            )
            .where(CATALOG_EPIS.c.ativo.is_(True))
            .order_by(CATALOG_EPIS.c.nome, CATALOG_EPIS.c.id)
        ).all()
        sector_rows = self._session.execute(
            select(CATALOG_SECTORS.c.id, CATALOG_SECTORS.c.nome)
            .where(CATALOG_SECTORS.c.ativo.is_(True))
            .order_by(CATALOG_SECTORS.c.nome, CATALOG_SECTORS.c.id)
        ).all()
        return (
            tuple(
                CameraRecord(
                    id=int(row.id),
                    name=str(row.nome),
                    description=_text(row.descricao),
                    stream_source=str(row.endereco),
                )
                for row in camera_rows
            ),
            tuple(
                EpiRecord(
                    id=int(row.id),
                    name=str(row.nome),
                    code=_text(row.codigo),
                    description=_text(row.descricao),
                )
                for row in epi_rows
            ),
            tuple(SectorRecord(id=int(row.id), name=str(row.nome)) for row in sector_rows),
        )

    def create_camera(
        self,
        *,
        name: str,
        description: str | None,
        stream_source: str,
        sector_id: int,
        active: bool,
    ) -> CameraRecord:
        self._require_active_sector(sector_id)
        self._ensure_camera_name_available(name)
        created_id = self._session.scalar(
            insert(CATALOG_CAMERAS)
            .values(
                nome=name,
                descricao=description,
                endereco=stream_source,
                setor_id=sector_id,
                ativa=active,
                criado_em=datetime.now(UTC),
            )
            .returning(CATALOG_CAMERAS.c.id)
        )
        if created_id is None:
            raise RuntimeError("a câmera não recebeu identificador")
        camera_id = int(created_id)
        self._session.commit()
        return self.get_camera(camera_id)

    def get_camera(self, camera_id: int) -> CameraRecord:
        row = self._session.execute(
            select(
                CATALOG_CAMERAS.c.id,
                CATALOG_CAMERAS.c.nome,
                CATALOG_CAMERAS.c.descricao,
                CATALOG_CAMERAS.c.endereco,
            ).where(CATALOG_CAMERAS.c.id == camera_id)
        ).one_or_none()
        if row is None:
            raise OperationConfigurationNotFoundError("câmera não encontrada")
        return CameraRecord(
            id=int(row.id),
            name=str(row.nome),
            description=_text(row.descricao),
            stream_source=str(row.endereco),
        )

    def list_risk_areas(self, camera_id: int | None = None) -> tuple[RiskAreaRecord, ...]:
        statement = self._risk_area_statement().order_by(RISK_AREAS.c.nome, RISK_AREAS.c.id)
        if camera_id is not None:
            statement = statement.where(RISK_AREAS.c.camera_id == camera_id)
        rows = self._session.execute(statement).mappings()
        return tuple(self._risk_area_from_row(dict(row)) for row in rows)

    def get_risk_area(self, risk_area_id: int) -> RiskAreaRecord:
        row = (
            self._session.execute(
                self._risk_area_statement().where(RISK_AREAS.c.id == risk_area_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OperationConfigurationNotFoundError("área de risco não encontrada")
        return self._risk_area_from_row(dict(row))

    def create_risk_area(
        self,
        *,
        camera_id: int,
        name: str,
        geometry: dict[str, Any],
        active: bool,
    ) -> RiskAreaRecord:
        self._require_active_camera(camera_id)
        self._ensure_area_name_available(camera_id=camera_id, name=name)
        now = datetime.now(UTC)
        created_id = self._session.scalar(
            insert(RISK_AREAS)
            .values(
                camera_id=camera_id,
                nome=name,
                geometria=geometry,
                ativa=active,
                criado_em=now,
                atualizado_em=now,
            )
            .returning(RISK_AREAS.c.id)
        )
        if created_id is None:
            raise RuntimeError("a área de risco não recebeu identificador")
        risk_area_id = int(created_id)
        self._session.commit()
        return self.get_risk_area(risk_area_id)

    def update_risk_area(
        self,
        risk_area_id: int,
        *,
        camera_id: int,
        name: str,
        geometry: dict[str, Any],
        active: bool,
    ) -> RiskAreaRecord:
        self.get_risk_area(risk_area_id)
        self._require_active_camera(camera_id)
        self._ensure_area_name_available(camera_id=camera_id, name=name, excluded_id=risk_area_id)
        self._session.execute(
            update(RISK_AREAS)
            .where(RISK_AREAS.c.id == risk_area_id)
            .values(
                camera_id=camera_id,
                nome=name,
                geometria=geometry,
                ativa=active,
                atualizado_em=datetime.now(UTC),
            )
        )
        self._session.commit()
        return self.get_risk_area(risk_area_id)

    def list_operations(self, *, active_only: bool = False) -> tuple[OperationRecord, ...]:
        statement = self._operation_statement().order_by(OPERATIONS.c.nome, OPERATIONS.c.id)
        if active_only:
            statement = statement.where(OPERATIONS.c.ativa.is_(True), RISK_AREAS.c.ativa.is_(True))
        rows = tuple(self._session.execute(statement).mappings())
        if not rows:
            return ()
        operation_ids = tuple(int(row["id"]) for row in rows)
        ppe_rows = self._session.execute(
            select(
                OPERATION_EPIS.c.operacao_id,
                CATALOG_EPIS.c.id,
                CATALOG_EPIS.c.nome,
                CATALOG_EPIS.c.codigo,
                CATALOG_EPIS.c.descricao,
            )
            .select_from(
                OPERATION_EPIS.join(CATALOG_EPIS, CATALOG_EPIS.c.id == OPERATION_EPIS.c.epi_id)
            )
            .where(OPERATION_EPIS.c.operacao_id.in_(operation_ids))
            .order_by(OPERATION_EPIS.c.operacao_id, CATALOG_EPIS.c.nome)
        ).all()
        by_operation: dict[int, list[EpiRecord]] = {value: [] for value in operation_ids}
        for row in ppe_rows:
            by_operation[int(row.operacao_id)].append(
                EpiRecord(
                    id=int(row.id),
                    name=str(row.nome),
                    code=_text(row.codigo),
                    description=_text(row.descricao),
                )
            )
        return tuple(
            self._operation_from_row(dict(row), tuple(by_operation[int(row["id"])])) for row in rows
        )

    def get_operation(self, operation_id: int) -> OperationRecord:
        items = tuple(item for item in self.list_operations() if item.id == operation_id)
        if not items:
            raise OperationConfigurationNotFoundError("operação não encontrada")
        return items[0]

    def create_operation(
        self,
        *,
        name: str,
        description: str | None,
        epi_ids: tuple[int, ...],
        risk_area_id: int,
        active: bool,
    ) -> OperationRecord:
        self._validate_operation_references(epi_ids, risk_area_id)
        self._ensure_operation_name_available(name)
        now = datetime.now(UTC)
        created_id = self._session.scalar(
            insert(OPERATIONS)
            .values(
                nome=name,
                descricao=description,
                area_risco_id=risk_area_id,
                ativa=active,
                criado_em=now,
                atualizado_em=now,
            )
            .returning(OPERATIONS.c.id)
        )
        if created_id is None:
            raise RuntimeError("a operação não recebeu identificador")
        operation_id = int(created_id)
        self._replace_operation_epis(operation_id, epi_ids, now)
        self._session.commit()
        return self.get_operation(operation_id)

    def update_operation(
        self,
        operation_id: int,
        *,
        name: str,
        description: str | None,
        epi_ids: tuple[int, ...],
        risk_area_id: int,
        active: bool,
    ) -> OperationRecord:
        self.get_operation(operation_id)
        self._validate_operation_references(epi_ids, risk_area_id)
        self._ensure_operation_name_available(name, excluded_id=operation_id)
        now = datetime.now(UTC)
        self._session.execute(
            update(OPERATIONS)
            .where(OPERATIONS.c.id == operation_id)
            .values(
                nome=name,
                descricao=description,
                area_risco_id=risk_area_id,
                ativa=active,
                atualizado_em=now,
            )
        )
        self._replace_operation_epis(operation_id, epi_ids, now)
        self._session.commit()
        return self.get_operation(operation_id)

    def _risk_area_statement(self) -> Select[Any]:
        return select(
            RISK_AREAS.c.id,
            RISK_AREAS.c.camera_id,
            CATALOG_CAMERAS.c.nome.label("camera_name"),
            RISK_AREAS.c.nome.label("name"),
            RISK_AREAS.c.geometria.label("geometry"),
            RISK_AREAS.c.ativa.label("active"),
            RISK_AREAS.c.criado_em.label("created_at"),
            RISK_AREAS.c.atualizado_em.label("updated_at"),
        ).select_from(
            RISK_AREAS.join(CATALOG_CAMERAS, CATALOG_CAMERAS.c.id == RISK_AREAS.c.camera_id)
        )

    def _operation_statement(self) -> Select[Any]:
        return select(
            OPERATIONS.c.id,
            OPERATIONS.c.nome.label("name"),
            OPERATIONS.c.descricao.label("description"),
            OPERATIONS.c.ativa.label("active"),
            OPERATIONS.c.criado_em.label("created_at"),
            OPERATIONS.c.atualizado_em.label("updated_at"),
            RISK_AREAS.c.id.label("risk_id"),
            RISK_AREAS.c.camera_id,
            CATALOG_CAMERAS.c.nome.label("camera_name"),
            RISK_AREAS.c.nome.label("risk_name"),
            RISK_AREAS.c.geometria.label("geometry"),
            RISK_AREAS.c.ativa.label("risk_active"),
            RISK_AREAS.c.criado_em.label("risk_created_at"),
            RISK_AREAS.c.atualizado_em.label("risk_updated_at"),
        ).select_from(
            OPERATIONS.join(RISK_AREAS, RISK_AREAS.c.id == OPERATIONS.c.area_risco_id).join(
                CATALOG_CAMERAS, CATALOG_CAMERAS.c.id == RISK_AREAS.c.camera_id
            )
        )

    def _require_active_camera(self, camera_id: int) -> None:
        value = self._session.scalar(
            select(CATALOG_CAMERAS.c.id).where(
                CATALOG_CAMERAS.c.id == camera_id,
                CATALOG_CAMERAS.c.ativa.is_(True),
            )
        )
        if value is None:
            raise OperationConfigurationNotFoundError("câmera ativa não encontrada")

    def _require_active_sector(self, sector_id: int) -> None:
        value = self._session.scalar(
            select(CATALOG_SECTORS.c.id).where(
                CATALOG_SECTORS.c.id == sector_id,
                CATALOG_SECTORS.c.ativo.is_(True),
            )
        )
        if value is None:
            raise OperationConfigurationNotFoundError("setor ativo não encontrado")

    def _validate_operation_references(self, epi_ids: tuple[int, ...], risk_area_id: int) -> None:
        area = self.get_risk_area(risk_area_id)
        if not area.active:
            raise OperationConfigurationConflictError("a área de risco está inativa")
        found = set(
            int(value)
            for value in self._session.scalars(
                select(CATALOG_EPIS.c.id).where(
                    CATALOG_EPIS.c.id.in_(epi_ids), CATALOG_EPIS.c.ativo.is_(True)
                )
            )
        )
        if found != set(epi_ids):
            raise OperationConfigurationNotFoundError("um ou mais EPIs ativos não existem")

    def _ensure_area_name_available(
        self, *, camera_id: int, name: str, excluded_id: int | None = None
    ) -> None:
        statement = select(RISK_AREAS.c.id).where(
            RISK_AREAS.c.camera_id == camera_id,
            func.lower(RISK_AREAS.c.nome) == name.casefold(),
        )
        if excluded_id is not None:
            statement = statement.where(RISK_AREAS.c.id != excluded_id)
        if self._session.scalar(statement) is not None:
            raise OperationConfigurationConflictError(
                "já existe uma área com esse nome para a câmera"
            )

    def _ensure_operation_name_available(self, name: str, excluded_id: int | None = None) -> None:
        statement = select(OPERATIONS.c.id).where(func.lower(OPERATIONS.c.nome) == name.casefold())
        if excluded_id is not None:
            statement = statement.where(OPERATIONS.c.id != excluded_id)
        if self._session.scalar(statement) is not None:
            raise OperationConfigurationConflictError("já existe uma operação com esse nome")

    def _ensure_camera_name_available(self, name: str) -> None:
        value = self._session.scalar(
            select(CATALOG_CAMERAS.c.id).where(
                func.lower(CATALOG_CAMERAS.c.nome) == name.casefold()
            )
        )
        if value is not None:
            raise OperationConfigurationConflictError("já existe uma câmera com esse nome")

    def _replace_operation_epis(
        self, operation_id: int, epi_ids: tuple[int, ...], created_at: datetime
    ) -> None:
        self._session.execute(
            delete(OPERATION_EPIS).where(OPERATION_EPIS.c.operacao_id == operation_id)
        )
        self._session.execute(
            insert(OPERATION_EPIS),
            [
                {"operacao_id": operation_id, "epi_id": epi_id, "criado_em": created_at}
                for epi_id in epi_ids
            ],
        )

    @staticmethod
    def _risk_area_from_row(row: dict[str, Any]) -> RiskAreaRecord:
        return RiskAreaRecord(
            id=int(row["id"]),
            camera_id=int(row["camera_id"]),
            camera_name=str(row["camera_name"]),
            name=str(row["name"]),
            geometry=dict(row["geometry"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _operation_from_row(
        row: dict[str, Any], required_ppe: tuple[EpiRecord, ...]
    ) -> OperationRecord:
        area = RiskAreaRecord(
            id=int(row["risk_id"]),
            camera_id=int(row["camera_id"]),
            camera_name=str(row["camera_name"]),
            name=str(row["risk_name"]),
            geometry=dict(row["geometry"]),
            active=bool(row["risk_active"]),
            created_at=row["risk_created_at"],
            updated_at=row["risk_updated_at"],
        )
        return OperationRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            description=_text(row["description"]),
            required_ppe=required_ppe,
            risk_area=area,
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "CameraRecord",
    "EpiRecord",
    "OperationConfigurationConflictError",
    "OperationConfigurationNotFoundError",
    "OperationRecord",
    "OperationRepository",
    "RiskAreaRecord",
    "SectorRecord",
]
