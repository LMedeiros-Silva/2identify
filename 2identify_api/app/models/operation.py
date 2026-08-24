"""SQL views for operation configuration tables managed through this API."""

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, column, table

CATALOG_EPIS = table(
    "epis",
    column("id", Integer),
    column("nome", String(100)),
    column("codigo", String(50)),
    column("descricao", String(500)),
    column("ativo", Boolean),
)

CATALOG_CAMERAS = table(
    "cameras",
    column("id", Integer),
    column("nome", String(100)),
    column("descricao", String(255)),
    column("endereco", String(500)),
    column("setor_id", Integer),
    column("ativa", Boolean),
    column("criado_em", DateTime(timezone=True)),
)

CATALOG_SECTORS = table(
    "setores",
    column("id", Integer),
    column("nome", String(100)),
    column("ativo", Boolean),
)

RISK_AREAS = table(
    "areas_risco",
    column("id", Integer),
    column("camera_id", Integer),
    column("nome", String(120)),
    column("geometria", JSON),
    column("ativa", Boolean),
    column("criado_em", DateTime(timezone=True)),
    column("atualizado_em", DateTime(timezone=True)),
)

OPERATIONS = table(
    "operacoes",
    column("id", Integer),
    column("nome", String(150)),
    column("descricao", String(500)),
    column("area_risco_id", Integer),
    column("ativa", Boolean),
    column("criado_em", DateTime(timezone=True)),
    column("atualizado_em", DateTime(timezone=True)),
)

OPERATION_EPIS = table(
    "operacao_epis",
    column("operacao_id", Integer),
    column("epi_id", Integer),
    column("criado_em", DateTime(timezone=True)),
)

__all__ = [
    "CATALOG_CAMERAS",
    "CATALOG_EPIS",
    "CATALOG_SECTORS",
    "OPERATIONS",
    "OPERATION_EPIS",
    "RISK_AREAS",
]
