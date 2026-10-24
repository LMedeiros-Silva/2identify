"""Read-only public alert panel served apart from the authenticated API.

The panel runs in its own process and port, so exposing it to the audience
(for example through a tunnel) never exposes Admin, Operator or device routes.
"""

from app.public_panel.app import create_public_app

__all__ = ["create_public_app"]
