"""Reusable navigation sidebar for authenticated Operator screens."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

WORKS_ROUTE = "works"


class Sidebar(QFrame):
    """Present navigation routes and emit user intent without owning navigation."""

    route_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, app_version: str) -> None:
        super().__init__()
        self._navigation_buttons: dict[str, QPushButton] = {}
        self._selected_route: str | None = None

        self.setObjectName("mainSidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(248)
        self._build_content(app_version)
        self.select_route(WORKS_ROUTE, emit_signal=False)

    @property
    def selected_route(self) -> str | None:
        return self._selected_route

    def select_route(self, route: str, emit_signal: bool = True) -> None:
        """Select a registered route and optionally announce the user intent."""

        if route not in self._navigation_buttons:
            raise ValueError(f"Rota lateral desconhecida: {route}")

        self._selected_route = route
        for button_route, button in self._navigation_buttons.items():
            button.setProperty("selected", button_route == route)
            self._refresh_style(button)

        if emit_signal:
            self.route_requested.emit(route)

    def _build_content(self, app_version: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(0)
        layout.addLayout(self._build_brand())
        layout.addSpacing(40)
        layout.addWidget(self._label("NAVEGAÇÃO", "sidebarSectionLabel"))
        layout.addSpacing(10)
        self._add_navigation_button(layout, WORKS_ROUTE, "Trabalhos")
        layout.addStretch(1)

        separator = QFrame()
        separator.setObjectName("sidebarSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        layout.addSpacing(14)

        logout_button = QPushButton("Sair")
        logout_button.setObjectName("sidebarLogoutButton")
        logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_button.setAccessibleName("Sair da sessão")
        logout_button.clicked.connect(self.logout_requested)
        layout.addWidget(logout_button)
        layout.addSpacing(16)

        version = self._label(f"Versão {app_version}", "sidebarVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

    def _build_brand(self) -> QHBoxLayout:
        brand = QHBoxLayout()
        brand.setSpacing(11)

        mark = self._label("2I", "sidebarBrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(38, 38)
        brand.addWidget(mark)

        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self._label("2IDENTIFY", "sidebarBrandName"))
        names.addWidget(self._label("OPERATOR", "sidebarProductName"))
        brand.addLayout(names)
        brand.addStretch(1)
        return brand

    def _add_navigation_button(
        self,
        layout: QVBoxLayout,
        route: str,
        label: str,
    ) -> None:
        button = QPushButton(label)
        button.setObjectName("sidebarNavigationButton")
        button.setProperty("route", route)
        button.setProperty("selected", False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(label)
        button.clicked.connect(self._handle_navigation_click)
        self._navigation_buttons[route] = button
        layout.addWidget(button)

    @Slot()
    def _handle_navigation_click(self) -> None:
        button = self.sender()
        if not isinstance(button, QPushButton):
            return
        route = button.property("route")
        if isinstance(route, str):
            self.select_route(route)

    @staticmethod
    def _refresh_style(button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
