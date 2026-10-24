"""Configurações: what this Admin is connected to and who is signed in.

Read-only: the API address comes from the Admin ``.env`` and is never edited
here. "Testar conexão" asks the dashboard for a fresh summary from the API.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.safety_widgets import StateChip

_PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def app_version() -> str:
    try:
        with _PYPROJECT.open("rb") as file:
            return str(tomllib.load(file)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "—"


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class _Panel(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("settings_panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        head = QFrame()
        head.setObjectName("settings_row")
        self._head = QHBoxLayout(head)
        self._head.setContentsMargins(16, 12, 16, 12)
        self._head.addWidget(_label(title, "settings_title"), 1)
        self._layout.addWidget(head)

    def add_chip(self, chip: QWidget) -> None:
        self._head.addWidget(chip)

    def add_row(self, key: str, value: QWidget, action: QWidget | None = None) -> None:
        row = QFrame()
        row.setObjectName("settings_row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        key_label = _label(key, "settings_key")
        key_label.setFixedWidth(150)
        layout.addWidget(key_label)
        layout.addWidget(value, 1)
        if action is not None:
            layout.addWidget(action)
        self._layout.addWidget(row)

    def finish(self) -> None:
        self._layout.addStretch()


class SettingsPage(QWidget):
    test_requested = Signal()
    logout_requested = Signal()

    def __init__(self, api_url: str, user_name: str, username: str, profile: str) -> None:
        super().__init__()
        self.setObjectName("settings_page")
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        api = _Panel("Conexão com a API")
        self.api_chip = StateChip("Aguardando", "inc")
        api.add_chip(self.api_chip)
        address = _label(api_url, "settings_code")
        address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        api.add_row("Endereço", address)
        self.last_response = _label("Ainda não consultada", "settings_value")
        self.test_button = QPushButton("Testar conexão")
        self.test_button.setObjectName("settings_button")
        self.test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_button.clicked.connect(self._request_test)
        api.add_row("Última resposta", self.last_response, self.test_button)
        api.add_row(
            "Origem do endereço", _label("Arquivo .env do Admin (API_URL)", "settings_muted")
        )
        api.finish()
        layout.addWidget(api, 0, 0)

        realtime = _Panel("Alertas em tempo real")
        self.realtime_chip = StateChip("Desconectado", "warn")
        realtime.add_chip(self.realtime_chip)
        self.realtime_detail = _label("Canal ainda não conectado.", "settings_value")
        realtime.add_row("Canal", self.realtime_detail)
        realtime.add_row(
            "Se cair",
            _label("O Admin tenta reconectar sozinho e mostra o estado no topo.", "settings_muted"),
        )
        realtime.finish()
        layout.addWidget(realtime, 0, 1)

        session = _Panel("Sessão")
        session.add_row("Usuário", _label(f"{user_name} · {username}", "settings_value"))
        logout = QPushButton("Sair")
        logout.setObjectName("settings_logout")
        logout.setCursor(Qt.CursorShape.PointingHandCursor)
        logout.clicked.connect(self.logout_requested.emit)
        session.add_row("Perfil", _label(profile.capitalize(), "settings_value"), logout)
        session.finish()
        layout.addWidget(session, 1, 0)

        about = _Panel("Sobre")
        about.add_row("Aplicativo", _label("2Identify Admin", "settings_value"))
        about.add_row("Versão", _label(app_version(), "settings_value"))
        about.finish()
        layout.addWidget(about, 1, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(2, 1)

    def _request_test(self) -> None:
        self.test_button.setEnabled(False)
        self.last_response.setText("Consultando a API...")
        self.test_requested.emit()

    def show_api_ok(self, when: datetime) -> None:
        local = when.astimezone()
        self.api_chip.set_state("Conectada", "safe")
        self.last_response.setText(f"{local:%d/%m/%Y} às {local:%H:%M:%S}")
        self.test_button.setEnabled(True)

    def show_api_error(self, message: str) -> None:
        self.api_chip.set_state("Sem resposta", "crit")
        self.last_response.setText(message)
        self.test_button.setEnabled(True)

    def set_realtime_status(self, message: str, *, state: str) -> None:
        if state == "connected":
            self.realtime_chip.set_state("Conectado", "safe")
            self.realtime_detail.setText("Novos alertas chegam sem atualizar a tela.")
        elif state == "connecting":
            self.realtime_chip.set_state("Conectando", "inc")
            self.realtime_detail.setText(message)
        else:
            self.realtime_chip.set_state("Desconectado", "warn")
            self.realtime_detail.setText(message)
