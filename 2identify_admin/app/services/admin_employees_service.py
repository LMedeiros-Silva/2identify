"""Admin-facing employee and Face ID workflows through the API."""

from __future__ import annotations

from typing import Protocol

from app.domain.employees import (
    EmployeeDraft,
    EmployeePage,
    EmployeeRecord,
    FaceTemplateDraft,
    FaceTemplateStatus,
)
from app.domain.operations import OperationCatalog, SectorOption
from app.services.errors import InvalidApiResponseError


class EmployeeProvider(Protocol):
    def get_employees(self, access_token: str, *, limit: int, offset: int) -> EmployeePage: ...
    def get_operation_catalog(self, access_token: str) -> OperationCatalog: ...
    def save_employee(
        self, access_token: str, draft: EmployeeDraft, employee_id: int | None = None
    ) -> EmployeeRecord: ...
    def save_face_template(
        self, access_token: str, employee_id: int, draft: FaceTemplateDraft
    ) -> FaceTemplateStatus: ...


class AdminEmployeesService:
    def __init__(self, provider: EmployeeProvider) -> None:
        self._provider = provider

    def load(
        self, access_token: str
    ) -> tuple[tuple[EmployeeRecord, ...], tuple[SectorOption, ...]]:
        records: list[EmployeeRecord] = []
        offset = 0
        while True:
            page = self._provider.get_employees(access_token, limit=100, offset=offset)
            if page.offset != offset or page.limit != 100:
                raise InvalidApiResponseError("Paginação de funcionários inconsistente.")
            if not page.items:
                if offset < page.total:
                    raise InvalidApiResponseError("A API interrompeu a lista de funcionários.")
                break
            records.extend(page.items)
            offset += len(page.items)
            if offset >= page.total:
                break
        sectors = self._provider.get_operation_catalog(access_token).sectors
        return tuple(records), sectors

    def save_employee(
        self, access_token: str, draft: EmployeeDraft, employee_id: int | None
    ) -> EmployeeRecord:
        return self._provider.save_employee(access_token, draft, employee_id)

    def save_face_template(
        self, access_token: str, employee_id: int, template: FaceTemplateDraft
    ) -> FaceTemplateStatus:
        return self._provider.save_face_template(access_token, employee_id, template)


__all__ = ["AdminEmployeesService"]
