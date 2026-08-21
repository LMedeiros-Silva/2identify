"""Read-only SQL expression models for the Admin-owned dashboard tables.

These lightweight table clauses intentionally stay outside ``Base.metadata``: the API can
query the reconciled columns without claiming DDL or migration ownership.
"""

from sqlalchemy import Boolean, Integer, String, column, table

FUNCIONARIOS = table(
    "funcionarios",
    column("id", Integer),
    column("ativo", Boolean),
)

FUNCIONARIO_EPIS = table(
    "funcionario_epis",
    column("id", Integer),
    column("entregue", Boolean),
)

ALERTAS = table(
    "alertas",
    column("id", Integer),
    column("nivel", String(30)),
)

__all__ = ["ALERTAS", "FUNCIONARIO_EPIS", "FUNCIONARIOS"]
