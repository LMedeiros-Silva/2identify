"""Executable entry point for 2Identify Operator."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from app import __version__
from app.bootstrap import create_runtime, run_desktop, run_startup_check


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="2identify-operator")
    parser.add_argument(
        "--check",
        action="store_true",
        help="valida a configuração e encerra sem abrir a interface",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    args, qt_arguments = build_parser().parse_known_args(arguments)

    try:
        runtime = create_runtime()
        if args.check:
            return run_startup_check(runtime)
        return run_desktop(runtime, [sys.argv[0], *qt_arguments])
    except Exception:
        # A configuração do logging pode ser justamente o ponto da falha de bootstrap.
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger(__name__).exception("operator_startup_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

