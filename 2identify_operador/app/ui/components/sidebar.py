"""Reusable navigation sidebar for authenticated Operator screens."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui.icons import line_icon
from app.ui.theme import TOKENS

WORKS_ROUTE = "works"


class Sidebar(QFrame):
    """Present navigation routes and emit user intent without owning navigation."""

    route_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, app_version: str) -> None:
        super().__init__()
        self._navigation_buttons: dict[str, QPushButton] = {}
        self._button_labels: dict[QPushButton, str] = {}
        self._selected_icons: dict[str, object] = {}
        self._expanded_only: list[QLabel] = []
        self._selected_route: str | None = None
        self._compact = False

        self.setObjectName("mainSidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(248)
        self._build_content(app_version)
        self.select_route(WORKS_ROUTE, emit_signal=False)

    @property
    def selected_route(self) -> str | None:
        return self._selected_route

    @property
    def is_compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool) -> None:
        """Collapse to an icon rail so monitoring keeps the space for cameras."""

        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self.setFixedWidth(72)
        else:
            self.setMinimumWidth(210)
            self.setMaximumWidth(248)
        for label in self._expanded_only:
            label.setVisible(not compact)
        for button, text in self._button_labels.items():
            button.setText("" if compact else text)
            button.setToolTip(text if compact else "")
        self._layout.setContentsMargins(*((12, 22, 12, 18) if compact else (18, 22, 18, 18)))
        self.setProperty("compact", compact)
        self._refresh_style(self)

    def select_route(self, route: str, emit_signal: bool = True) -> None:
        """Select a registered route and optionally announce the user intent."""

        if route not in self._navigation_buttons:
            raise ValueError(f"Rota lateral desconhecida: {route}")

        self._selected_route = route
        for button_route, button in self._navigation_buttons.items():
            button.setProperty("selected", button_route == route)
            if button_route == route and button_route in self._selected_icons:
                button.setIcon(self._selected_icons[button_route])
            self._refresh_style(button)

        if emit_signal:
            self.route_requested.emit(route)

    def _build_content(self, app_version: str) -> None:
        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(0)
        layout.addLayout(self._build_brand())
        layout.addSpacing(40)
        section = self._label("NAVEGAÇÃO", "sidebarSectionLabel")
        self._expanded_only.append(section)
        layout.addWidget(section)
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
        logout_button.setIcon(
            line_icon("logout", TOKENS["nav_muted"], active_color=TOKENS["crit_300"])
        )
        logout_button.setIconSize(QSize(18, 18))
        self._button_labels[logout_button] = "Sair"
        layout.addWidget(logout_button)
        layout.addSpacing(16)

        version = self._label(f"Versão {app_version}", "sidebarVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._expanded_only.append(version)
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
        for text, name in (("2IDENTIFY", "sidebarBrandName"), ("OPERATOR", "sidebarProductName")):
            label = self._label(text, name)
            self._expanded_only.append(label)
            names.addWidget(label)
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
        button.setIcon(line_icon(route, TOKENS["nav_muted"], active_color=TOKENS["surface_1"]))
        self._selected_icons[route] = line_icon(route, TOKENS["surface_1"])
        button.setIconSize(QSize(18, 18))
        self._button_labels[button] = label
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
    def _refresh_style(button: QFrame) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
