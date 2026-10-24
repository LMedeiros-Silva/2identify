"""Sanitized, read-only projection of persisted alerts for the audience.

Only non-personal columns are selected: no employee, operator or admin names,
no registration, evidence paths, confidence or Admin observations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OPERATIONS,
    PERSISTED_SAFETY_ALERTS,
    SAFETY_CAMERAS,
    SAFETY_OCCURRENCES,
    SAFETY_SECTORS,
    SafetyAlertIngestion,
)
from app.schemas.realtime import normalize_public_summary

_CATEGORY_BY_TYPE = {
    "fall_detected": "fall",
    "fall": "fall",
    "queda": "fall",
    "ppe_absent": "ppe",
    "ppe": "ppe",
    "epi": "ppe",
    "epi_ausente": "ppe",
    "person_in_risk_area": "risk_area",
    "risk_area": "risk_area",
    "area_risco": "risk_area",
    "ergonomic_risk": "ergonomics",
    "ergonomics": "ergonomics",
    "ergonomia": "ergonomics",
    "monitoring_interrupted": "monitoring",
    "monitoring": "monitoring",
}
_DEFAULT_TITLE = {
    "fall": "Queda detectada",
    "ppe": "EPI obrigatório ausente",
    "risk_area": "Entrada na área de risco",
    "ergonomics": "Postura de risco",
    "monitoring": "Monitoramento interrompido",
    "inconclusive": "Verificação de EPI inconclusiva",
    "safety": "Alerta de segurança",
}
_STATUS = {"nao_lido": "novo", "lido": "confirmado", "encerrado": "encerrado"}
_MAX_TITLE = 160


@dataclass(frozen=True, slots=True)
class PublicAlert:
    id: int
    category: str
    severity: str
    title: str
    status: str
    condition: str
    camera: str | None
    sector: str | None
    operation: str | None
    created_at: str
    updated_at: str

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _category(violation_type: str | None, occurrence_type: str | None, subject: str | None) -> str:
    if violation_type == "monitoring_interrupted" and (subject or "").startswith(
        "ppe_inconclusive:"
    ):
        return "inconclusive"
    for value in (violation_type, occurrence_type):
        key = (value or "").strip().casefold()
        if key in _CATEGORY_BY_TYPE:
            return _CATEGORY_BY_TYPE[key]
    return "safety"


def _title(description: str | None, category: str) -> str:
    try:
        title = normalize_public_summary(description or "")
    except ValueError:
        return _DEFAULT_TITLE[category]
    return title if len(title) <= _MAX_TITLE else f"{title[: _MAX_TITLE - 1]}…"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_public_summary(value)[:100]
    except ValueError:
        return None


class PublicAlertRepository:
    """Newest alerts first, limited to a small window."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def recent(self, limit: int) -> list[PublicAlert]:
        alerts = PERSISTED_SAFETY_ALERTS
        occurrences = SAFETY_OCCURRENCES
        cameras = SAFETY_CAMERAS
        sectors = SAFETY_SECTORS
        ingestion = SafetyAlertIngestion.__table__
        operations = OPERATIONS
        statement = (
            select(
                alerts.c.id,
                alerts.c.nivel,
                alerts.c.status,
                alerts.c.criado_em,
                alerts.c.confirmado_em,
                alerts.c.encerrado_em,
                occurrences.c.tipo,
                occurrences.c.descricao,
                cameras.c.nome.label("camera"),
                sectors.c.nome.label("sector"),
                ingestion.c.violacao_tipo,
                ingestion.c.assunto_chave,
                ingestion.c.alerta_id.label("ingested"),
                ingestion.c.condicao_resolvida_em,
                operations.c.nome.label("operation"),
            )
            .select_from(
                alerts.join(occurrences, occurrences.c.id == alerts.c.ocorrencia_id)
                .outerjoin(cameras, cameras.c.id == occurrences.c.camera_id)
                .outerjoin(sectors, sectors.c.id == cameras.c.setor_id)
                .outerjoin(ingestion, ingestion.c.alerta_id == alerts.c.id)
                .outerjoin(operations, operations.c.id == ingestion.c.operacao_id)
            )
            .order_by(alerts.c.criado_em.desc(), alerts.c.id.desc())
            .limit(limit)
        )
        return [self._to_public(row) for row in self._session.execute(statement).mappings()]

    @staticmethod
    def _to_public(row) -> PublicAlert:  # type: ignore[no-untyped-def]
        category = _category(row["violacao_tipo"], row["tipo"], row["assunto_chave"])
        status = _STATUS.get(str(row["status"] or "").strip().casefold(), "novo")
        if str(row["nivel"] or "").casefold() == "critical":
            severity = "critical"
        elif category in {"inconclusive", "monitoring"}:
            severity = "inconclusive"
        else:
            severity = "warning"
        if row["condicao_resolvida_em"] is not None:
            condition = "resolvida"
        elif row["ingested"] is None:
            condition = "desconhecida"
        else:
            condition = "ativa"
        moments = [
            _utc(value)
            for value in (
                row["criado_em"],
                row["confirmado_em"],
                row["encerrado_em"],
                row["condicao_resolvida_em"],
            )
            if value is not None
        ]
        created = _iso(row["criado_em"]) or ""
        updated = _iso(max(moments, default=None)) or created
        return PublicAlert(
            id=int(row["id"]),
            category=category,
            severity=severity,
            title=_title(row["descricao"], category),
            status=status,
            condition=condition,
            camera=_clean(row["camera"]),
            sector=_clean(row["sector"]),
            operation=_clean(row["operation"]),
            created_at=created,
            updated_at=updated,
        )
