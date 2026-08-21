"""Versioned contracts emitted by the administrative realtime stream."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RealtimeEventType = Literal[
    "connection.ready",
    "connection.heartbeat",
    "alert.created",
]

_DATA_URI_PATTERN = re.compile(r"(?i)(?:^|\s)data:[^,\s]+,")
_BASE64_BLOB_PATTERN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{80,}={0,2}(?!\S)")
_LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:file://|(?:^|\s)[a-z]:[\\/]|\\\\[^\\\s]+[\\/]|"
    r"(?:^|\s)/(?:home|users|var|tmp|etc|opt)/)"
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_CPF_PATTERN = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?55[\s.-]*)?\(?\d{2}\)?[\s.-]*9?\d{4}[\s.-]*\d{4}(?!\d)"
)
_PII_LABEL_PATTERN = re.compile(
    r"(?i)\b(?:cpf|e-?mail|telefone|celular|phone|matr[ií]cula|"
    r"nome\s+(?:do|da)(?:\s+[^\s:]+){0,4})\s*:"
)


class StreamReadyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: Literal["awaiting_alert_ingestion"]


class StreamHeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AlertCreatedPayload(BaseModel):
    """Future committed-alert payload; no producer exists in this stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    alert_id: Annotated[int, Field(gt=0)]
    occurrence_id: Annotated[int, Field(gt=0)]
    level: Literal["warning", "critical"]
    status: Literal["nao_lido", "lido", "encerrado"]
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    detected_at: datetime
    camera_id: Annotated[int, Field(gt=0)] | None = None

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        if any(unicodedata.category(character).startswith("C") for character in value):
            raise ValueError("summary contém caracteres de controle")
        normalized = re.sub(r"\s+", " ", value.strip())
        if not normalized:
            raise ValueError("summary não pode ser vazio")
        if (
            _DATA_URI_PATTERN.search(normalized)
            or ";base64," in normalized.casefold()
            or _BASE64_BLOB_PATTERN.search(normalized)
            or _LOCAL_PATH_PATTERN.search(normalized)
        ):
            raise ValueError("summary não pode conter imagem ou caminho local")
        if (
            _EMAIL_PATTERN.search(normalized)
            or _CPF_PATTERN.search(normalized)
            or _PHONE_PATTERN.search(normalized)
            or _PII_LABEL_PATTERN.search(normalized)
        ):
            raise ValueError("summary não pode conter PII")
        return normalized

    @field_validator("detected_at")
    @classmethod
    def require_detected_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at deve possuir fuso horário")
        return value.astimezone(UTC)


RealtimeEventPayload = StreamReadyPayload | StreamHeartbeatPayload | AlertCreatedPayload


class RealtimeEventEnvelope(BaseModel):
    """Stable JSON envelope shared by readiness, heartbeat and future alert events."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    event_id: UUID = Field(default_factory=uuid4)
    event_type: RealtimeEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: RealtimeEventPayload

    @field_validator("occurred_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at deve possuir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_matching_payload(self) -> RealtimeEventEnvelope:
        expected_payload = {
            "connection.ready": StreamReadyPayload,
            "connection.heartbeat": StreamHeartbeatPayload,
            "alert.created": AlertCreatedPayload,
        }[self.event_type]
        if not isinstance(self.payload, expected_payload):
            raise ValueError("payload incompatível com event_type")
        if (
            isinstance(self.payload, AlertCreatedPayload)
            and self.payload.detected_at > self.occurred_at + timedelta(minutes=5)
        ):
            raise ValueError("detected_at não pode exceder occurred_at em mais de 5 minutos")
        return self

    def as_json_message(self) -> dict[str, object]:
        """Return only JSON-compatible values for a WebSocket frame."""

        return cast(dict[str, object], self.model_dump(mode="json"))


def stream_ready_event() -> RealtimeEventEnvelope:
    """Describe the truthful current capability of the stream."""

    return RealtimeEventEnvelope(
        event_type="connection.ready",
        payload=StreamReadyPayload(status="awaiting_alert_ingestion"),
    )


def stream_heartbeat_event() -> RealtimeEventEnvelope:
    """Keep idle authenticated connections observable without claiming alert ingestion."""

    return RealtimeEventEnvelope(
        event_type="connection.heartbeat",
        payload=StreamHeartbeatPayload(),
    )


__all__ = [
    "AlertCreatedPayload",
    "RealtimeEventEnvelope",
    "RealtimeEventPayload",
    "RealtimeEventType",
    "StreamHeartbeatPayload",
    "StreamReadyPayload",
    "stream_heartbeat_event",
    "stream_ready_event",
]
