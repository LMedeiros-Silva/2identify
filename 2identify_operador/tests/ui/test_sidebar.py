import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from app.ui.components.sidebar import WORKS_ROUTE, Sidebar


def test_sidebar_starts_with_works_selected(qtbot) -> None:
    sidebar = Sidebar("0.1.0")
    qtbot.addWidget(sidebar)
    sidebar.show()

    works_button = sidebar.findChild(QPushButton, "sidebarNavigationButton")
    assert sidebar.selected_route == WORKS_ROUTE
    assert works_button.text() == "Trabalhos"
    assert works_button.property("selected") is True


def test_sidebar_emits_selected_route(qtbot) -> None:
    sidebar = Sidebar("0.1.0")
    qtbot.addWidget(sidebar)
    sidebar.show()
    works_button = sidebar.findChild(QPushButton, "sidebarNavigationButton")

    with qtbot.waitSignal(sidebar.route_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(works_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [WORKS_ROUTE]


def test_sidebar_emits_logout_intent(qtbot) -> None:
    sidebar = Sidebar("0.1.0")
    qtbot.addWidget(sidebar)
    sidebar.show()
    logout_button = sidebar.findChild(QPushButton, "sidebarLogoutButton")

    with qtbot.waitSignal(sidebar.logout_requested, timeout=1_000):
        qtbot.mouseClick(logout_button, Qt.MouseButton.LeftButton)


def test_sidebar_rejects_unknown_route(qtbot) -> None:
    sidebar = Sidebar("0.1.0")
    qtbot.addWidget(sidebar)

    with pytest.raises(ValueError, match="Rota lateral desconhecida"):
        sidebar.select_route("unknown")
