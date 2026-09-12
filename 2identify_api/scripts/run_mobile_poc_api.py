"""Run the existing FastAPI application against Supabase in an isolated child process."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT
from app.mobile_poc.config import (
    MobilePocConfigurationError,
    MobilePocDatabaseConfig,
    load_mobile_poc_database_config,
)


def build_mobile_api_environment(
    config: MobilePocDatabaseConfig,
    mobile_env_path: Path,
    parent_environment: Mapping[str, str],
) -> dict[str, str]:
    """Build an isolated environment without mutating or retaining cloud aliases."""

    child = dict(parent_environment)
    child["DATABASE_URL"] = config.cloud_sqlalchemy_url
    child.pop("CLOUD_DATABASE_URL", None)
    mobile_values = dotenv_values(mobile_env_path) if mobile_env_path.is_file() else {}
    origins = mobile_values.get("MOBILE_CORS_ORIGINS")
    if isinstance(origins, str) and origins.strip():
        child["MOBILE_CORS_ORIGINS"] = origins.strip()
    else:
        child.pop("MOBILE_CORS_ORIGINS", None)
    return child


def startup_message(config: MobilePocDatabaseConfig, *, host: str, port: int) -> str:
    return (
        f"API mobile iniciando em {host}:{port} com destino "
        f"{config.masked_cloud_target}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_mobile_poc_database_config()
        child_environment = build_mobile_api_environment(
            config,
            PROJECT_ROOT / ".env.mobile",
            os.environ,
        )
    except MobilePocConfigurationError as error:
        print(f"API MOBILE INTERROMPIDA: {type(error).__name__}", file=sys.stderr)
        return 2

    print(startup_message(config, host=args.host, port=args.port))
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        cwd=PROJECT_ROOT,
        env=child_environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
