"""Bind locally staged RTSP sources to real catalog IDs after Admin registration."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_STAGED_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")


def _assignment(value: str, label: str) -> tuple[str, str]:
    left, separator, right = value.partition("=")
    if not separator or not left or not right:
        raise ValueError(f"{label} deve usar NOME=VALOR")
    return left.strip(), right.strip()


def _camera_id(value: str) -> int:
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError("camera_id deve ser inteiro positivo")
    return int(value)


def build_bindings(
    values: dict[str, str | None],
    cameras: list[str],
    usb: list[str],
) -> dict[int, str]:
    """Resolve sources without returning or logging any credential-bearing locator."""

    bindings: dict[int, str] = {}
    for assignment in cameras:
        staged_name, camera_id_text = _assignment(assignment, "--camera")
        if not _STAGED_NAME.fullmatch(staged_name):
            raise ValueError("nome da fonte preparada inválido")
        camera_id = _camera_id(camera_id_text)
        source = values.get(f"CAMERA_STAGED_{staged_name}")
        parsed = urlsplit(source or "")
        if parsed.scheme.casefold() not in {"rtsp", "http", "https"} or not parsed.hostname:
            raise ValueError(f"fonte local inválida ou ausente: {staged_name}")
        if camera_id in bindings:
            raise ValueError("camera_id repetido")
        bindings[camera_id] = source
    for assignment in usb:
        camera_id_text, index_text = _assignment(assignment, "--usb")
        camera_id = _camera_id(camera_id_text)
        if not index_text.isdecimal():
            raise ValueError("índice USB deve ser inteiro não negativo")
        if camera_id in bindings:
            raise ValueError("camera_id repetido")
        bindings[camera_id] = str(int(index_text))
    if not bindings:
        raise ValueError("informe pelo menos uma câmera")
    return bindings


def write_bindings(env_file: Path, bindings: dict[int, str], *, replace: bool) -> None:
    if not env_file.is_file():
        raise ValueError(".env local não encontrado")
    current = dotenv_values(env_file)
    for camera_id, source in bindings.items():
        existing = current.get(f"CAMERA_SOURCE_{camera_id}")
        if existing is not None and existing != source and not replace:
            raise ValueError(f"CAMERA_SOURCE_{camera_id} já existe; use --replace para trocar")
    names = {f"CAMERA_SOURCE_{camera_id}" for camera_id in bindings}
    lines = [
        line for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.partition("=")[0].strip() not in names
    ]
    lines.extend(f"CAMERA_SOURCE_{camera_id}={source}" for camera_id, source in bindings.items())
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--camera", action="append", default=[], metavar="NOME=ID")
    parser.add_argument("--usb", action="append", default=[], metavar="ID=INDICE")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        bindings = build_bindings(
            dotenv_values(args.env_file), args.camera, args.usb
        )
        write_bindings(args.env_file, bindings, replace=args.replace)
    except ValueError as error:
        parser.error(str(error))
    for camera_id in bindings:
        print(f"CAMERA_SOURCE_{camera_id}=CONFIGURADO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
