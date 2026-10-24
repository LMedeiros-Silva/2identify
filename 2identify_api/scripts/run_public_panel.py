"""Start the public, read-only alert panel on its own port.

    python -m scripts.run_public_panel --host 0.0.0.0 --port 8100

Expose only this port to the audience (a tunnel or the venue Wi-Fi); the
authenticated API on port 8000 stays private.
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    arguments = parser.parse_args()
    uvicorn.run(
        "app.public_panel:create_public_app",
        factory=True,
        host=arguments.host,
        port=arguments.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        # Open live streams would otherwise hold Ctrl+C until every phone leaves.
        timeout_graceful_shutdown=2,
    )


if __name__ == "__main__":
    main()
