"""Administrative alert listing and lifecycle use cases."""

from __future__ import annotations

from typing import cast

from app.repositories.admin_alert_repository import (
    AdminAlertRecord,
    AdminAlertRepository,
)
from app.schemas.admin_alerts import (
    AdminAlertActor,
    AdminAlertCamera,
    AdminAlertCategory,
    AdminAlertDetail,
    AdminAlertEmployee,
    AdminAlertLevel,
    AdminAlertList,
    AdminAlertOccurrence,
    AdminAlertOperationalContext,
    AdminAlertSector,
    AdminAlertStatus,
    ensure_aware,
)


class AdminAlertsService:
    def __init__(self, repository: AdminAlertRepository) -> None:
        self._repository = repository

    def list_alerts(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: str | None,
    ) -> AdminAlertList:
        records, total = self._repository.list(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
        return AdminAlertList(
            items=tuple(self._to_detail(record) for record in records),
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_alert(self, alert_id: int) -> AdminAlertDetail:
        return self._to_detail(self._repository.get(alert_id))

    def confirm_alert(
        self,
        alert_id: int,
        *,
        administrator_id: int,
        observation: str | None,
    ) -> AdminAlertDetail:
        return self._to_detail(
            self._repository.confirm(
                alert_id,
                administrator_id=administrator_id,
                observation=_optional_text(observation),
            )
        )

    def close_alert(
        self,
        alert_id: int,
        *,
        administrator_id: int,
        observation: str | None,
    ) -> AdminAlertDetail:
        return self._to_detail(
            self._repository.close(
                alert_id,
                administrator_id=administrator_id,
                observation=_optional_text(observation),
            )
        )

    @staticmethod
    def _to_detail(record: AdminAlertRecord) -> AdminAlertDetail:
        employee_sector = _sector(
            record.employee_sector_id,
            record.employee_sector_name,
        )
        camera_sector = _sector(record.camera_sector_id, record.camera_sector_name)
        employee = None
        if record.employee_id is not None and record.employee_name and record.employee_registration:
            employee = AdminAlertEmployee(
                id=record.employee_id,
                name=record.employee_name,
                registration=record.employee_registration,
                role=_optional_text(record.employee_role),
                shift=_optional_text(record.employee_shift),
                sector=employee_sector,
            )
        camera = None
        if record.camera_id is not None and record.camera_name:
            camera = AdminAlertCamera(
                id=record.camera_id,
                name=record.camera_name,
                description=_optional_text(record.camera_description),
                sector=camera_sector,
            )
        operational_context = None
        if (
            record.event_id is not None
            and record.work_session_id is not None
            and record.operation_id is not None
            and record.violation_type
            and record.subject_key
            and record.ingestion_received_at is not None
        ):
            operational_context = AdminAlertOperationalContext(
                event_id=record.event_id,
                work_session_id=record.work_session_id,
                operation_id=record.operation_id,
                operation_name=_optional_text(record.operation_name),
                risk_area_id=record.risk_area_id,
                violation_type=record.violation_type,
                subject_key=record.subject_key,
                operator=_actor(record.operator_id, record.operator_name),
                received_at=ensure_aware(record.ingestion_received_at),
            )
        summary = (
            _optional_text(record.occurrence_description)
            or _optional_text(record.observation)
            or record.occurrence_type.strip()
        )
        return AdminAlertDetail(
            id=record.alert_id,
            category=_category(record.violation_type or record.occurrence_type),
            level=_level(record.level),
            status=_status(record.status),
            summary=summary,
            observation=_optional_text(record.observation),
            created_at=ensure_aware(record.created_at),
            received_at=(
                ensure_aware(record.received_at) if record.received_at is not None else None
            ),
            confirmed_at=(
                ensure_aware(record.confirmed_at) if record.confirmed_at is not None else None
            ),
            confirmed_by=_actor(
                record.confirmed_by_id,
                record.confirmed_by_name,
            ),
            closed_at=(ensure_aware(record.closed_at) if record.closed_at is not None else None),
            closed_by=_actor(record.closed_by_id, record.closed_by_name),
            occurrence=AdminAlertOccurrence(
                id=record.occurrence_id,
                type=record.occurrence_type.strip(),
                description=_optional_text(record.occurrence_description),
                confidence=record.confidence,
                image_reference=_optional_text(record.image_reference),
                video_reference=_optional_text(record.video_reference),
                detected_at=ensure_aware(record.detected_at),
                employee=employee,
                camera=camera,
            ),
            operational_context=operational_context,
        )


def _category(value: str) -> AdminAlertCategory:
    normalized = value.strip().casefold()
    category = {
        "ergonomic_risk": "ergonomics",
        "ppe_absent": "ppe",
        "person_in_risk_area": "risk_area",
        "monitoring_interrupted": "monitoring",
    }.get(normalized, "safety")
    return cast(AdminAlertCategory, category)


def _level(value: str) -> AdminAlertLevel:
    return "critical" if value.strip().casefold() in {"critico", "critical"} else "warning"


def _status(value: str) -> AdminAlertStatus:
    normalized = value.strip().casefold()
    if normalized not in {"nao_lido", "lido", "encerrado"}:
        return "nao_lido"
    return cast(AdminAlertStatus, normalized)


def _actor(actor_id: int | None, name: str | None) -> AdminAlertActor | None:
    if actor_id is None or not name or not name.strip():
        return None
    return AdminAlertActor(id=actor_id, name=name.strip())


def _sector(sector_id: int | None, name: str | None) -> AdminAlertSector | None:
    if sector_id is None or not name or not name.strip():
        return None
    return AdminAlertSector(id=sector_id, name=name.strip())


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


__all__ = ["AdminAlertsService"]
