"""Create the ignored mobile PoC environment through a non-echoing prompt."""

from __future__ import annotations

import argparse
import getpass
import os
import socket
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.mobile_poc.config import (
    MobilePocConfigurationError,
    MobilePocDatabaseConfig,
    validate_mobile_database_targets,
)


def _local_database_url(local_env_path: Path) -> str:
    local_values = dotenv_values(local_env_path) if local_env_path.is_file() else {}
    raw_value = os.environ.get("DATABASE_URL") or local_values.get("DATABASE_URL")
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise MobilePocConfigurationError("DATABASE_URL local não foi configurada")
    return raw_value


def _normalized_origins(raw_value: str) -> str:
    try:
        origins = Settings.parse_mobile_cors_origins(raw_value)
    except (TypeError, ValueError, ValidationError) as error:
        raise MobilePocConfigurationError(
            "MOBILE_CORS_ORIGINS contém uma origem inválida"
        ) from error
    if not origins:
        raise MobilePocConfigurationError(
            "MOBILE_CORS_ORIGINS deve informar ao menos uma origem"
        )
    return ",".join(origins)


def configure_mobile_environment(
    *,
    local_env_path: Path,
    mobile_env_path: Path,
    cloud_database_url: str,
    cors_origins: str,
    force: bool = False,
) -> MobilePocDatabaseConfig:
    """Validate and atomically write only the isolated mobile environment."""

    if local_env_path.resolve() == mobile_env_path.resolve():
        raise MobilePocConfigurationError("o arquivo mobile deve permanecer isolado")
    if mobile_env_path.exists() and not force:
        raise MobilePocConfigurationError("o arquivo .env.mobile já existe")

    config = validate_mobile_database_targets(
        _local_database_url(local_env_path),
        cloud_database_url,
    )
    normalized_origins = _normalized_origins(cors_origins)
    contents = (
        f"CLOUD_DATABASE_URL={config.cloud_sqlalchemy_url}\n"
        f"MOBILE_CORS_ORIGINS={normalized_origins}\n"
    )

    mobile_env_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=mobile_env_path.parent,
            prefix=".env.mobile.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(contents)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, mobile_env_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return config


def discover_mobile_origins(*, frontend_port: int = 5173) -> tuple[str, ...]:
    """Return exact localhost and likely LAN origins without contacting a service."""

    origins = [
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            local_address = str(connection.getsockname()[0])
        if local_address and not local_address.startswith("127."):
            origins.append(f"http://{local_address}:{frontend_port}")
    except OSError:
        pass
    return tuple(origins)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        help="Origem HTTP exata permitida; repita para adicionar outras.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Substitui somente o .env.mobile existente após nova validação.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    origins = tuple(args.cors_origins or discover_mobile_origins())
    cloud_database_url = getpass.getpass(
        "Cole CLOUD_DATABASE_URL do Supabase (entrada oculta): "
    )
    try:
        config = configure_mobile_environment(
            local_env_path=PROJECT_ROOT / ".env",
            mobile_env_path=PROJECT_ROOT / ".env.mobile",
            cloud_database_url=cloud_database_url,
            cors_origins=",".join(origins),
            force=args.force,
        )
    except MobilePocConfigurationError as error:
        print(f"CONFIGURAÇÃO INTERROMPIDA: {type(error).__name__}", file=sys.stderr)
        return 2
    finally:
        cloud_database_url = ""

    print(f"Configuração mobile criada para {config.masked_cloud_target}.")
    print("A configuração local original permaneceu intacta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
