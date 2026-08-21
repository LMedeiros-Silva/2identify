"""Generate a persistent local JWT secret without printing it."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
SETTING_NAME = "AUTH_TOKEN_SECRET"


def _is_usable_secret(value: str) -> bool:
    normalized = value.strip()
    return (
        len(normalized.encode("utf-8")) >= 32
        and not normalized.casefold().startswith(("change_me", "generate_"))
    )


def ensure_auth_secret(env_path: Path = ENV_PATH) -> bool:
    """Ensure the local environment has a strong secret; return True when changed."""

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    setting_prefix = f"{SETTING_NAME}="
    replacement = f"{setting_prefix}{secrets.token_urlsafe(48)}"
    changed = False
    found = False
    updated_lines: list[str] = []

    for line in lines:
        if line.startswith(setting_prefix):
            found = True
            current_value = line.removeprefix(setting_prefix)
            if _is_usable_secret(current_value):
                updated_lines.append(line)
            else:
                updated_lines.append(replacement)
                changed = True
        else:
            updated_lines.append(line)

    if not found:
        if updated_lines and updated_lines[-1] != "":
            updated_lines.append("")
        updated_lines.append(replacement)
        changed = True

    if not changed:
        return False

    temporary_path = env_path.with_name(f"{env_path.name}.tmp")
    temporary_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    os.replace(temporary_path, env_path)
    return True


def main() -> int:
    changed = ensure_auth_secret()
    state = "gerado" if changed else "já configurado"
    print(f"Segredo de autenticação {state}; nenhum valor foi exibido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
