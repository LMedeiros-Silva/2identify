"""Print a sanitized JSON snapshot of the configured PostgreSQL schema."""

from __future__ import annotations

import json
import sys

from app.core.config import get_settings
from app.core.database import DatabaseManager, DatabaseUnavailableError
from app.core.schema_inspection import inspect_database_schema


def main() -> int:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        snapshot = inspect_database_schema(database, settings.database_schema)
    except DatabaseUnavailableError:
        print("Falha ao inspecionar o PostgreSQL configurado.", file=sys.stderr)
        return 1
    finally:
        database.dispose()

    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
