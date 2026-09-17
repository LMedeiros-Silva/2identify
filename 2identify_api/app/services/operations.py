"""Operation and normalized risk-area configuration use cases."""

from __future__ import annotations

from app.repositories.operation_repository import (
    CameraRecord,
    EpiRecord,
    OperationRecord,
    OperationRepository,
    RiskAreaRecord,
    SectorRecord,
)
from app.schemas.operations import (
    AdminCameraItem,
    CameraCatalogItem,
    CameraWrite,
    EpiReference,
    OperationCatalog,
    OperationDetail,
    OperationWrite,
    OperatorCameraItem,
    PolygonGeometry,
    RiskAreaDetail,
    RiskAreaWrite,
    SectorCatalogItem,
)
from app.services.camera_sources import (
    classify_camera_source,
    public_camera_source,
    sanitized_admin_source,
)


class OperationsService:
    def __init__(self, repository: OperationRepository) -> None:
        self._repository = repository

    def get_catalog(self) -> OperationCatalog:
        cameras, epis, sectors = self._repository.catalog()
        return OperationCatalog(
            cameras=tuple(self._camera(item) for item in cameras),
            epis=tuple(self._epi(item) for item in epis),
            sectors=tuple(self._sector(item) for item in sectors),
        )

    def create_camera(self, payload: CameraWrite) -> CameraCatalogItem:
        return self._camera(
            self._repository.create_camera(
                name=payload.name,
                description=payload.description,
                stream_source=payload.stream_source,
                sector_id=payload.sector_id,
                active=payload.active,
            )
        )

    def list_risk_areas(self, camera_id: int | None = None) -> tuple[RiskAreaDetail, ...]:
        return tuple(self._risk_area(item) for item in self._repository.list_risk_areas(camera_id))

    def create_risk_area(self, payload: RiskAreaWrite) -> RiskAreaDetail:
        return self._risk_area(
            self._repository.create_risk_area(
                camera_id=payload.camera_id,
                name=payload.name,
                geometry=payload.geometry.model_dump(mode="json"),
                active=payload.active,
            )
        )

    def update_risk_area(self, risk_area_id: int, payload: RiskAreaWrite) -> RiskAreaDetail:
        return self._risk_area(
            self._repository.update_risk_area(
                risk_area_id,
                camera_id=payload.camera_id,
                name=payload.name,
                geometry=payload.geometry.model_dump(mode="json"),
                active=payload.active,
            )
        )

    def list_operations(self, *, active_only: bool = False) -> tuple[OperationDetail, ...]:
        return tuple(
            self._operation(item)
            for item in self._repository.list_operations(active_only=active_only)
        )

    def get_operation(self, operation_id: int) -> OperationDetail:
        return self._operation(self._repository.get_operation(operation_id))

    def list_operator_cameras(self, operation_id: int) -> tuple[OperatorCameraItem, ...]:
        return tuple(
            OperatorCameraItem(
                id=item.id,
                name=item.name,
                sector_id=item.sector_id,
                source_type=classify_camera_source(item.stream_source).value,
                source_hint=public_camera_source(item.stream_source),
            )
            for item in self._repository.list_active_cameras_for_operation(operation_id)
        )

    def list_cameras(self, sector_id: int | None = None) -> tuple[AdminCameraItem, ...]:
        return tuple(self._admin_camera(item) for item in self._repository.list_cameras(sector_id))

    def update_camera(self, camera_id: int, payload: CameraWrite) -> AdminCameraItem:
        existing = self._repository.get_camera(camera_id)
        source = (
            existing.stream_source
            if payload.stream_source == sanitized_admin_source(existing.stream_source)
            else payload.stream_source
        )
        return self._admin_camera(
            self._repository.update_camera(
                camera_id,
                name=payload.name,
                description=payload.description,
                stream_source=source,
                sector_id=payload.sector_id,
                active=payload.active,
            )
        )

    def create_operation(self, payload: OperationWrite) -> OperationDetail:
        return self._operation(
            self._repository.create_operation(
                name=payload.name,
                description=payload.description,
                epi_ids=tuple(payload.epi_ids),
                risk_area_id=payload.risk_area_id,
                active=payload.active,
            )
        )

    def update_operation(self, operation_id: int, payload: OperationWrite) -> OperationDetail:
        return self._operation(
            self._repository.update_operation(
                operation_id,
                name=payload.name,
                description=payload.description,
                epi_ids=tuple(payload.epi_ids),
                risk_area_id=payload.risk_area_id,
                active=payload.active,
            )
        )

    @staticmethod
    def _epi(item: EpiRecord) -> EpiReference:
        return EpiReference(
            id=item.id,
            name=item.name,
            code=item.code,
            description=item.description,
        )

    @staticmethod
    def _camera(item: CameraRecord) -> CameraCatalogItem:
        return CameraCatalogItem(
            id=item.id,
            name=item.name,
            description=item.description,
            stream_source=sanitized_admin_source(item.stream_source),
        )

    @classmethod
    def _admin_camera(cls, item: CameraRecord) -> AdminCameraItem:
        return AdminCameraItem(
            **cls._camera(item).model_dump(), sector_id=item.sector_id, active=item.active
        )

    @staticmethod
    def _sector(item: SectorRecord) -> SectorCatalogItem:
        return SectorCatalogItem(id=item.id, name=item.name)

    @staticmethod
    def _risk_area(item: RiskAreaRecord) -> RiskAreaDetail:
        return RiskAreaDetail(
            id=item.id,
            camera_id=item.camera_id,
            camera_name=item.camera_name,
            name=item.name,
            geometry=PolygonGeometry.model_validate(item.geometry),
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @classmethod
    def _operation(cls, item: OperationRecord) -> OperationDetail:
        return OperationDetail(
            id=item.id,
            name=item.name,
            description=item.description,
            required_ppe=tuple(cls._epi(ppe) for ppe in item.required_ppe),
            risk_area=cls._risk_area(item.risk_area),
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


__all__ = ["OperationsService"]
