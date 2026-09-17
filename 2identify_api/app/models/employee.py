"""SQL views of Admin-owned employees and API-owned face templates."""

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, column, table

EMPLOYEES = table(
    "funcionarios",
    column("id", Integer),
    column("nome", String(150)),
    column("matricula", String(50)),
    column("cargo", String(100)),
    column("turno", String(50)),
    column("foto", String(500)),
    column("ativo", Boolean),
    column("setor_id", Integer),
    column("criado_em", DateTime(timezone=True)),
    column("atualizado_em", DateTime(timezone=True)),
)

EMPLOYEE_FACE_TEMPLATES = table(
    "funcionario_face_templates",
    column("funcionario_id", Integer),
    column("model_id", String(80)),
    column("embedding", JSON),
    column("criado_em", DateTime(timezone=True)),
    column("atualizado_em", DateTime(timezone=True)),
)

__all__ = ["EMPLOYEES", "EMPLOYEE_FACE_TEMPLATES"]
