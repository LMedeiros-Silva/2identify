"""Read-only view of Admin face templates for server-side Face ID matching."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee import EMPLOYEE_FACE_TEMPLATES, EMPLOYEES


@dataclass(frozen=True, slots=True)
class EmployeeFaceTemplate:
    employee_id: int
    name: str
    embedding: tuple[float, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FaceAuthorizedEmployee:
    employee_id: int
    name: str


class FaceIdentityRepository:
    """Only active employees with an enrolled face can open a Face ID session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def templates(self, model_id: str) -> tuple[EmployeeFaceTemplate, ...]:
        rows = self._session.execute(
            select(EMPLOYEES.c.id, EMPLOYEES.c.nome, EMPLOYEE_FACE_TEMPLATES.c.embedding)
            .select_from(
                EMPLOYEES.join(
                    EMPLOYEE_FACE_TEMPLATES,
                    EMPLOYEE_FACE_TEMPLATES.c.funcionario_id == EMPLOYEES.c.id,
                )
            )
            .where(
                EMPLOYEES.c.ativo.is_(True),
                EMPLOYEE_FACE_TEMPLATES.c.model_id == model_id,
            )
            .order_by(EMPLOYEES.c.id)
        ).all()
        templates: list[EmployeeFaceTemplate] = []
        for row in rows:
            name = (row.nome or "").strip()
            embedding = row.embedding
            if not name or not isinstance(embedding, list):
                continue
            try:
                templates.append(
                    EmployeeFaceTemplate(row.id, name, tuple(float(value) for value in embedding))
                )
            except (TypeError, ValueError):
                continue
        return tuple(templates)

    def find_authorized_employee(self, employee_id: int) -> FaceAuthorizedEmployee | None:
        row = self._session.execute(
            select(EMPLOYEES.c.id, EMPLOYEES.c.nome)
            .select_from(
                EMPLOYEES.join(
                    EMPLOYEE_FACE_TEMPLATES,
                    EMPLOYEE_FACE_TEMPLATES.c.funcionario_id == EMPLOYEES.c.id,
                )
            )
            .where(EMPLOYEES.c.id == employee_id, EMPLOYEES.c.ativo.is_(True))
        ).first()
        if row is None or not (row.nome or "").strip():
            return None
        return FaceAuthorizedEmployee(row.id, row.nome.strip())
