"""Static safety audit for Alembic upgrade functions used by the mobile PoC."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


class MigrationAuditError(RuntimeError):
    """Raised when an Alembic upgrade cannot be proven non-destructive."""


@dataclass(frozen=True)
class MigrationMetadata:
    path: Path
    revision: str
    down_revision: str | None


_EXPECTED_POST_STAMP = (
    "7b9d2e4f6a81",
    "c8f1e2a3b4d5",
    "e4a7b8c9d0e1",
)
_FORBIDDEN_CALL_NAMES = frozenset(
    {
        "alter_column",
        "drop_column",
        "drop_constraint",
        "drop_index",
        "drop_table",
    }
)
_FORBIDDEN_SQL = re.compile(
    r"\b(?:DROP|TRUNCATE|DELETE)\b|\bALTER\s+TABLE\b",
    flags=re.IGNORECASE,
)


def _assignment_literal(module: ast.Module, name: str) -> object:
    for statement in module.body:
        target_name: str | None = None
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            target_name = target.id if isinstance(target, ast.Name) else None
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            target_name = statement.target.id if isinstance(statement.target, ast.Name) else None
            value = statement.value
        if target_name == name and value is not None:
            try:
                return ast.literal_eval(value)
            except (ValueError, TypeError) as error:
                raise MigrationAuditError(f"metadado {name} não é literal") from error
    raise MigrationAuditError(f"migration sem metadado {name}")


def _load_metadata(path: Path) -> tuple[MigrationMetadata, ast.Module]:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    except (OSError, SyntaxError) as error:
        raise MigrationAuditError(f"não foi possível analisar migration {path.name}") from error
    revision = _assignment_literal(module, "revision")
    down_revision = _assignment_literal(module, "down_revision")
    if not isinstance(revision, str) or not (
        down_revision is None or isinstance(down_revision, str)
    ):
        raise MigrationAuditError(f"cadeia Alembic ambígua em {path.name}")
    return MigrationMetadata(path, revision, down_revision), module


def _upgrade_function(module: ast.Module, *, filename: str) -> ast.FunctionDef:
    for statement in module.body:
        if isinstance(statement, ast.FunctionDef) and statement.name == "upgrade":
            return statement
    raise MigrationAuditError(f"migration {filename} não possui upgrade()")


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _literal_sql(call: ast.Call) -> str | None:
    if not call.args:
        return None
    values = [node.value for node in ast.walk(call.args[0]) if isinstance(node, ast.Constant)]
    strings = [value for value in values if isinstance(value, str)]
    return " ".join(strings) if strings else None


def audit_migration_upgrade(
    path: Path,
    *,
    allowed_call_names: frozenset[str] = frozenset(),
) -> MigrationMetadata:
    """Reject any destructive or uninspectable operation in one upgrade function."""

    metadata, module = _load_metadata(path)
    upgrade = _upgrade_function(module, filename=path.name)
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        called_name = _called_name(node)
        if called_name in _FORBIDDEN_CALL_NAMES and called_name not in allowed_call_names:
            raise MigrationAuditError(
                f"migration {metadata.revision} contém operação proibida: {called_name}"
            )
        if called_name == "execute":
            sql = _literal_sql(node)
            if sql is None:
                raise MigrationAuditError(
                    f"migration {metadata.revision} contém SQL dinâmico não auditável"
                )
            if _FORBIDDEN_SQL.search(sql):
                raise MigrationAuditError(
                    f"migration {metadata.revision} contém SQL destrutivo"
                )
    return metadata


def read_migration_metadata(path: Path) -> MigrationMetadata:
    """Read only literal Alembic identifiers from one migration."""

    metadata, _ = _load_metadata(path)
    return metadata


def audit_post_stamp_migrations(versions_directory: Path) -> tuple[str, ...]:
    """Audit the exact linear chain approved between revision 441 and current head."""

    metadata_by_revision: dict[str, MigrationMetadata] = {}
    for path in sorted(versions_directory.glob("*.py")):
        metadata, _ = _load_metadata(path)
        metadata_by_revision[metadata.revision] = metadata

    current = "441c04c14c57"
    ordered: list[str] = []
    while True:
        if current == _EXPECTED_POST_STAMP[-1]:
            break
        children = sorted(
            (
                item
                for item in metadata_by_revision.values()
                if item.down_revision == current
            ),
            key=lambda item: item.revision,
        )
        if not children:
            break
        if len(children) != 1:
            raise MigrationAuditError("cadeia Alembic posterior possui ramificação inesperada")
        metadata = audit_migration_upgrade(children[0].path)
        ordered.append(metadata.revision)
        current = metadata.revision

    revisions = tuple(ordered)
    if revisions != _EXPECTED_POST_STAMP:
        raise MigrationAuditError("cadeia Alembic posterior difere da sequência aprovada")
    return revisions


__all__ = [
    "MigrationAuditError",
    "MigrationMetadata",
    "audit_migration_upgrade",
    "audit_post_stamp_migrations",
    "read_migration_metadata",
]
