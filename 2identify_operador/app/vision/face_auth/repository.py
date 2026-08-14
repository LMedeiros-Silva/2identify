"""Versioned local face-template repository for controlled development."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.vision.face_auth.errors import FaceAuthenticationUnavailableError
from app.vision.face_auth.types import RegisteredFaceTemplate

_STORE_VERSION = 1


class JsonFaceTemplateRepository:
    """Load local biometric templates; production must replace this with the API."""

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path

    def load_templates(self, model_id: str) -> Sequence[RegisteredFaceTemplate]:
        if not self._store_path.exists():
            return ()

        try:
            payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FaceAuthenticationUnavailableError(
                "O cadastro biométrico local não pôde ser lido."
            ) from error

        self._validate_header(payload, model_id)
        operators = payload.get("operators")
        if not isinstance(operators, list):
            raise FaceAuthenticationUnavailableError("Cadastro biométrico local inválido.")

        templates = tuple(self._parse_template(item, model_id) for item in operators)
        operator_ids = [template.operator_id for template in templates]
        if len(operator_ids) != len(set(operator_ids)):
            raise FaceAuthenticationUnavailableError(
                "O cadastro biométrico contém operadores duplicados."
            )
        return templates

    def upsert_template(self, template: RegisteredFaceTemplate) -> None:
        """Atomically update a development enrollment store."""

        existing = list(self.load_templates(template.model_id))
        by_id = {item.operator_id: item for item in existing}
        by_id[template.operator_id] = template
        payload = {
            "version": _STORE_VERSION,
            "model_id": template.model_id,
            "operators": [self._serialize(item) for item in sorted(by_id.values(), key=_id)],
        }

        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._store_path.with_suffix(self._store_path.suffix + ".tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary_path, self._store_path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise FaceAuthenticationUnavailableError(
                "Não foi possível atualizar o cadastro biométrico local."
            ) from error

    @staticmethod
    def _validate_header(payload: object, model_id: str) -> None:
        if not isinstance(payload, dict):
            raise FaceAuthenticationUnavailableError("Cadastro biométrico local inválido.")
        if payload.get("version") != _STORE_VERSION:
            raise FaceAuthenticationUnavailableError(
                "Versão do cadastro biométrico local não suportada."
            )
        if payload.get("model_id") != model_id:
            raise FaceAuthenticationUnavailableError(
                "Os templates faciais foram gerados por outro modelo."
            )

    @staticmethod
    def _parse_template(item: object, model_id: str) -> RegisteredFaceTemplate:
        if not isinstance(item, dict):
            raise FaceAuthenticationUnavailableError("Template facial local inválido.")
        try:
            embedding_values = item["embedding"]
            if not isinstance(embedding_values, list):
                raise TypeError
            embedding = tuple(float(value) for value in embedding_values)
            if len(embedding) < 32 or not all(math.isfinite(value) for value in embedding):
                raise ValueError
            operator_id = int(item["operator_id"])
            name = str(item["name"]).strip()
            photo = item.get("profile_photo_reference")
            photo_reference = str(photo).strip() if photo else None
            if operator_id <= 0 or not name:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise FaceAuthenticationUnavailableError("Template facial local inválido.") from error

        return RegisteredFaceTemplate(
            operator_id=operator_id,
            name=name,
            model_id=model_id,
            embedding=embedding,
            profile_photo_reference=photo_reference,
        )

    @staticmethod
    def _serialize(template: RegisteredFaceTemplate) -> dict[str, Any]:
        return {
            "operator_id": template.operator_id,
            "name": template.name,
            "profile_photo_reference": template.profile_photo_reference,
            "embedding": list(template.embedding),
        }


def _id(template: RegisteredFaceTemplate) -> int:
    return template.operator_id

