"""Employee CRUD and central face-template persistence through one DB session."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.employee import EMPLOYEE_FACE_TEMPLATES, EMPLOYEES
from app.models.operation import CATALOG_SECTORS
from app.schemas.admin_employees import (
    EmployeeDetail,
    EmployeeDraft,
    FaceTemplateDraft,
    FaceTemplateStatus,
)


class EmployeeNotFoundError(RuntimeError):
    pass


class EmployeeConflictError(RuntimeError):
    pass


class AdminEmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, *, limit: int, offset: int) -> tuple[tuple[EmployeeDetail, ...], int]:
        total = int(self._session.scalar(select(func.count(EMPLOYEES.c.id))) or 0)
        rows = self._session.execute(
            self._details().order_by(EMPLOYEES.c.nome, EMPLOYEES.c.id)
            .limit(limit).offset(offset)
        ).mappings()
        return tuple(self._detail(row) for row in rows), total

    def get(self, employee_id: int) -> EmployeeDetail:
        row = self._session.execute(
            self._details().where(EMPLOYEES.c.id == employee_id)
        ).mappings().one_or_none()
        if row is None:
            raise EmployeeNotFoundError("Funcionário não encontrado.")
        return self._detail(row)

    def create(self, draft: EmployeeDraft) -> EmployeeDetail:
        self._validate_sector(draft.sector_id)
        now = datetime.now(UTC)
        try:
            employee_id = self._session.scalar(
                insert(EMPLOYEES).values(
                    nome=draft.name,
                    matricula=draft.registration,
                    cargo=draft.role,
                    turno=draft.shift,
                    setor_id=draft.sector_id,
                    ativo=draft.active,
                    criado_em=now,
                    atualizado_em=now,
                ).returning(EMPLOYEES.c.id)
            )
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EmployeeConflictError("Matrícula já cadastrada ou setor inválido.") from error
        assert employee_id is not None
        return self.get(int(employee_id))

    def update(self, employee_id: int, draft: EmployeeDraft) -> EmployeeDetail:
        self.get(employee_id)
        self._validate_sector(draft.sector_id)
        try:
            self._session.execute(
                update(EMPLOYEES).where(EMPLOYEES.c.id == employee_id).values(
                    nome=draft.name,
                    matricula=draft.registration,
                    cargo=draft.role,
                    turno=draft.shift,
                    setor_id=draft.sector_id,
                    ativo=draft.active,
                    atualizado_em=datetime.now(UTC),
                )
            )
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EmployeeConflictError("Matrícula já cadastrada ou setor inválido.") from error
        return self.get(employee_id)

    def save_face_template(
        self, employee_id: int, draft: FaceTemplateDraft
    ) -> FaceTemplateStatus:
        self.get(employee_id)
        now = datetime.now(UTC)
        existing = self._session.scalar(
            select(EMPLOYEE_FACE_TEMPLATES.c.funcionario_id).where(
                EMPLOYEE_FACE_TEMPLATES.c.funcionario_id == employee_id
            )
        )
        if existing is None:
            self._session.execute(
                insert(EMPLOYEE_FACE_TEMPLATES).values(
                    funcionario_id=employee_id,
                    model_id=draft.model_id,
                    embedding=list(draft.embedding),
                    criado_em=now,
                    atualizado_em=now,
                )
            )
        else:
            self._session.execute(
                update(EMPLOYEE_FACE_TEMPLATES)
                .where(EMPLOYEE_FACE_TEMPLATES.c.funcionario_id == employee_id)
                .values(
                    model_id=draft.model_id,
                    embedding=list(draft.embedding),
                    atualizado_em=now,
                )
            )
        self._session.commit()
        return self.face_status(employee_id)

    def face_status(self, employee_id: int) -> FaceTemplateStatus:
        self.get(employee_id)
        row = self._session.execute(
            select(
                EMPLOYEE_FACE_TEMPLATES.c.model_id,
                EMPLOYEE_FACE_TEMPLATES.c.atualizado_em,
            ).where(EMPLOYEE_FACE_TEMPLATES.c.funcionario_id == employee_id)
        ).first()
        if row is None:
            raise EmployeeNotFoundError("Face ID ainda não cadastrado.")
        return FaceTemplateStatus(
            employee_id=employee_id, model_id=row.model_id,
            enrolled_at=_aware(row.atualizado_em),
        )

    def _validate_sector(self, sector_id: int) -> None:
        active = self._session.scalar(
            select(CATALOG_SECTORS.c.ativo).where(CATALOG_SECTORS.c.id == sector_id)
        )
        if active is not True:
            raise EmployeeConflictError("Setor ativo não encontrado.")

    @staticmethod
    def _details():
        employees = EMPLOYEES
        sectors = CATALOG_SECTORS
        return select(
            employees.c.id,
            employees.c.nome,
            employees.c.matricula,
            employees.c.cargo,
            employees.c.turno,
            employees.c.setor_id,
            employees.c.ativo,
            employees.c.criado_em,
            employees.c.atualizado_em,
            sectors.c.nome.label("setor_nome"),
        ).select_from(employees.join(sectors, sectors.c.id == employees.c.setor_id))

    @staticmethod
    def _detail(row) -> EmployeeDetail:
        return EmployeeDetail(
            id=row.id,
            name=row.nome,
            registration=row.matricula,
            role=row.cargo,
            shift=row.turno,
            sector_id=row.setor_id,
            sector_name=row.setor_nome,
            active=row.ativo,
            created_at=_aware(row.criado_em),
            updated_at=_aware(row.atualizado_em),
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = ["AdminEmployeeRepository", "EmployeeNotFoundError", "EmployeeConflictError"]
