from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.domain.realtime import (
    ConnectionReadyEvent,
    HeartbeatEvent,
    RealtimeAlert,
    RealtimeEvent,
)

MAX_REALTIME_MESSAGE_BYTES = 64 * 1024
_MAX_CLOCK_SKEW = timedelta(minutes=5)
_DATA_URI = re.compile(r"(?:^|\s)data:[^,\s]+,", re.IGNORECASE)
_LONG_BASE64 = re.compile(
    r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{80,}={0,2}(?!\S)"
)
_LOCAL_PATH = re.compile(
    r"(?:file://|(?:^|\s)[a-z]:[\\/]|\\\\[^\\\s]+[\\/]|"
    r"(?:^|\s)/(?:home|users|var|tmp|etc|opt)/)",
    re.IGNORECASE,
)
_EMAIL = re.compile(
    r"\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b",
    re.IGNORECASE,
)
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?55[\s.-]*)?\(?\d{2}\)?[\s.-]*"
    r"9?\d{4}[\s.-]*\d{4}(?!\d)"
)
_LABELED_PII = re.compile(
    r"\b(?:cpf|e-?mail|telefone|celular|phone|matr[ií]cula|"
    r"nome\s+(?:do|da)(?:\s+[^\s:]+){0,4})\s*:",
    re.IGNORECASE,
)


class InvalidRealtimeEventError(ValueError):
    """A mensagem não corresponde ao contrato WebSocket público."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _ReadyPayload(_StrictModel):
    status: Literal["awaiting_alert_ingestion"]


class _HeartbeatPayload(_StrictModel):
    pass


class _AlertPayload(_StrictModel):
    alert_id: PositiveInt
    occurrence_id: PositiveInt
    level: Literal["warning", "critical"]
    status: Literal["nao_lido", "lido", "encerrado"]
    summary: str = Field(min_length=1, max_length=500)
    detected_at: AwareDatetime
    camera_id: PositiveInt | None = None

    @field_validator("summary")
    @classmethod
    def reject_sensitive_or_non_display_content(cls, value: str) -> str:
        if any(
            unicodedata.category(character).startswith("C") for character in value
        ):
            raise ValueError("summary contém caractere de controle")
        normalized = re.sub(r"\s+", " ", value.strip())
        if not normalized or normalized != value:
            raise ValueError("summary deve estar normalizado")
        if any(
            pattern.search(normalized)
            for pattern in (
                _DATA_URI,
                _LONG_BASE64,
                _LOCAL_PATH,
                _EMAIL,
                _CPF,
                _PHONE,
                _LABELED_PII,
            )
        ) or ";base64," in normalized.casefold():
            raise ValueError("summary contém conteúdo não permitido")
        return normalized


class _EnvelopeBase(_StrictModel):
    schema_version: Literal[1]
    event_id: UUID
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def validate_utc_timestamp(self) -> _EnvelopeBase:
        _require_utc(self.occurred_at, field_name="occurred_at")
        return self


class _ReadyEnvelope(_EnvelopeBase):
    event_type: Literal["connection.ready"]
    payload: _ReadyPayload


class _HeartbeatEnvelope(_EnvelopeBase):
    event_type: Literal["connection.heartbeat"]
    payload: _HeartbeatPayload


class _AlertEnvelope(_EnvelopeBase):
    event_type: Literal["alert.created"]
    payload: _AlertPayload

    @model_validator(mode="after")
    def validate_detected_at(self) -> _AlertEnvelope:
        _require_utc(self.payload.detected_at, field_name="detected_at")
        if self.payload.detected_at > self.occurred_at + _MAX_CLOCK_SKEW:
            raise ValueError("detected_at não pode estar no futuro do evento")
        return self


_Envelope = Annotated[
    _ReadyEnvelope | _HeartbeatEnvelope | _AlertEnvelope,
    Field(discriminator="event_type"),
]
_ENVELOPE_ADAPTER: TypeAdapter[_Envelope] = TypeAdapter(_Envelope)


def parse_realtime_event(raw_message: str) -> RealtimeEvent:
    """Valida um envelope v1 sem aceitar campos, tipos ou chaves duplicadas."""

    try:
        encoded = raw_message.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise InvalidRealtimeEventError("Mensagem WebSocket inválida.") from error
    if not encoded or len(encoded) > MAX_REALTIME_MESSAGE_BYTES:
        raise InvalidRealtimeEventError("Mensagem WebSocket fora do limite permitido.")

    try:
        json.loads(raw_message, object_pairs_hook=_reject_duplicate_keys)
        envelope = _ENVELOPE_ADAPTER.validate_json(encoded, strict=True)
    except (UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise InvalidRealtimeEventError(
            "Mensagem WebSocket incompatível com o contrato v1."
        ) from error

    occurred_at = envelope.occurred_at.astimezone(UTC)
    if isinstance(envelope, _ReadyEnvelope):
        return ConnectionReadyEvent(
            event_id=envelope.event_id,
            occurred_at=occurred_at,
            status=envelope.payload.status,
        )
    if isinstance(envelope, _HeartbeatEnvelope):
        return HeartbeatEvent(
            event_id=envelope.event_id,
            occurred_at=occurred_at,
        )

    return RealtimeAlert(
        event_id=envelope.event_id,
        occurred_at=occurred_at,
        alert_id=envelope.payload.alert_id,
        occurrence_id=envelope.payload.occurrence_id,
        level=envelope.payload.level,
        status=envelope.payload.status,
        summary=envelope.payload.summary,
        detected_at=envelope.payload.detected_at.astimezone(UTC),
        camera_id=envelope.payload.camera_id,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON contém chave duplicada")
        result[key] = value
    return result


def _require_utc(value: datetime, *, field_name: str) -> None:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} deve estar em UTC")
