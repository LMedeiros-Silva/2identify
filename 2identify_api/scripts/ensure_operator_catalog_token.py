"""Provision one shared read-only operation-catalog token without printing it."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
API_ENV_PATH = API_ROOT / ".env"
OPERATOR_ENV_PATH = API_ROOT.parent / "2identify_operador" / ".env"
SETTING_NAME = "OPERATOR_CATALOG_TOKEN"


def _read_setting(path: Path) -> str | None:
    if not path.exists():
        return None
    prefix = f"{SETTING_NAME}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None


def _is_usable_token(value: str | None) -> bool:
    if value is None:
        return False
    return (
        len(value.encode("utf-8")) >= 32
        and not value.casefold().startswith(("change_me", "generate_"))
    )


def _write_setting(path: Path, value: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{SETTING_NAME}="
    replacement = f"{prefix}{value}"
    updated: list[str] = []
    found = False
    changed = False
    for line in lines:
        if line.startswith(prefix):
            found = True
            updated.append(replacement)
            changed = changed or line != replacement
        else:
            updated.append(line)
    if not found:
        if updated and updated[-1] != "":
            updated.append("")
        updated.append(replacement)
        changed = True
    if not changed:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return True


def ensure_operator_catalog_token(
    api_env_path: Path = API_ENV_PATH,
    operator_env_path: Path = OPERATOR_ENV_PATH,
) -> tuple[bool, bool]:
    """Synchronize one strong token and report which environment files changed."""

    api_token = _read_setting(api_env_path)
    operator_token = _read_setting(operator_env_path)
    usable_api_token = api_token if _is_usable_token(api_token) else None
    usable_operator_token = operator_token if _is_usable_token(operator_token) else None
    if (
        usable_api_token is not None
        and usable_operator_token is not None
        and not secrets.compare_digest(usable_api_token, usable_operator_token)
    ):
        raise ValueError(
            "API e Operador já possuem tokens de catálogo diferentes; "
            "nenhum arquivo foi alterado."
        )

    shared_token = usable_api_token or usable_operator_token or secrets.token_urlsafe(48)
    return (
        _write_setting(api_env_path, shared_token),
        _write_setting(operator_env_path, shared_token),
    )


def main() -> int:
    try:
        api_changed, operator_changed = ensure_operator_catalog_token()
    except ValueError as error:
        print(str(error))
        return 1
    state = "atualizado" if api_changed or operator_changed else "já configurado"
    print(f"Token de catálogo {state} nos dois módulos; nenhum valor foi exibido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
