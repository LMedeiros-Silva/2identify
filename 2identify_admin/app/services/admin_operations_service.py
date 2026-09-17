"""Desktop-facing operation configuration use cases."""

from __future__ import annotations

from typing import Protocol

from app.domain import (
    CameraDraft,
    CameraOption,
    ManagedCamera,
    OperationCatalog,
    OperationConfiguration,
    OperationDraft,
    RiskArea,
    RiskAreaDraft,
)


class AdminOperationsProvider(Protocol):
    def get_operation_catalog(self, access_token: str) -> OperationCatalog: ...
    def get_risk_areas(self, access_token: str) -> tuple[RiskArea, ...]: ...
    def get_operations(self, access_token: str) -> tuple[OperationConfiguration, ...]: ...
    def get_cameras(self, access_token: str) -> tuple[ManagedCamera, ...]: ...
    def create_camera(self, access_token: str, draft: CameraDraft) -> CameraOption: ...
    def save_camera(
        self, access_token: str, draft: CameraDraft, camera_id: int
    ) -> ManagedCamera: ...
    def save_risk_area(
        self, access_token: str, draft: RiskAreaDraft, risk_area_id: int | None = None
    ) -> RiskArea: ...
    def save_operation(
        self,
        access_token: str,
        draft: OperationDraft,
        operation_id: int | None = None,
    ) -> OperationConfiguration: ...


class AdminOperationsService:
    def __init__(self, provider: AdminOperationsProvider) -> None:
        self._provider = provider

    def load(
        self, token: str
    ) -> tuple[
        OperationCatalog,
        tuple[RiskArea, ...],
        tuple[OperationConfiguration, ...],
        tuple[ManagedCamera, ...],
    ]:
        return (
            self._provider.get_operation_catalog(token),
            self._provider.get_risk_areas(token),
            self._provider.get_operations(token),
            self._provider.get_cameras(token),
        )

    def save_risk_area(
        self, token: str, draft: RiskAreaDraft, risk_area_id: int | None
    ) -> RiskArea:
        return self._provider.save_risk_area(token, draft, risk_area_id)

    def create_camera(self, token: str, draft: CameraDraft) -> CameraOption:
        return self._provider.create_camera(token, draft)

    def save_camera(self, token: str, draft: CameraDraft, camera_id: int) -> ManagedCamera:
        return self._provider.save_camera(token, draft, camera_id)

    def save_operation(
        self, token: str, draft: OperationDraft, operation_id: int | None
    ) -> OperationConfiguration:
        return self._provider.save_operation(token, draft, operation_id)


__all__ = ["AdminOperationsProvider", "AdminOperationsService"]
