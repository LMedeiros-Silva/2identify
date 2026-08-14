"""Accessible password input with an integrated visibility control."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QToolButton


class PasswordInput(QFrame):
    """Composite password field styled as a single control."""

    return_pressed = Signal()
    text_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("passwordInput")
        self.setProperty("validationState", "normal")
        self.setProperty("focusState", "normal")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(6)

        self._editor = QLineEdit()
        self._editor.setObjectName("passwordLineEdit")
        self._editor.setFrame(False)
        self._editor.setEchoMode(QLineEdit.EchoMode.Password)
        self._editor.setPlaceholderText("Digite sua senha")
        self._editor.setMaxLength(256)
        self._editor.setAccessibleName("Senha")
        self._editor.installEventFilter(self)
        self._editor.returnPressed.connect(self.return_pressed)
        self._editor.textChanged.connect(self.text_changed)
        layout.addWidget(self._editor, 1)

        self._toggle_button = QToolButton()
        self._toggle_button.setObjectName("passwordToggleButton")
        self._toggle_button.setText("MOSTRAR")
        self._toggle_button.setCheckable(True)
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setAccessibleName("Mostrar senha")
        self._toggle_button.setToolTip("Mostrar senha")
        self._toggle_button.toggled.connect(self._toggle_visibility)
        layout.addWidget(self._toggle_button)

    @property
    def editor(self) -> QLineEdit:
        """Expose the actual editor for focus order and automated UI tests."""

        return self._editor

    def text(self) -> str:
        return self._editor.text()

    def clear(self) -> None:
        self._editor.clear()

    def focus_editor(self) -> None:
        self._editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_error(self, has_error: bool) -> None:
        self.setProperty("validationState", "error" if has_error else "normal")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._editor and event.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        }:
            is_focused = event.type() == QEvent.Type.FocusIn
            self.setProperty("focusState", "focused" if is_focused else "normal")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        return super().eventFilter(watched, event)

    @Slot(bool)
    def _toggle_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self._editor.setEchoMode(mode)
        self._toggle_button.setText("OCULTAR" if visible else "MOSTRAR")
        accessible_text = "Ocultar senha" if visible else "Mostrar senha"
        self._toggle_button.setAccessibleName(accessible_text)
        self._toggle_button.setToolTip(accessible_text)
        self._editor.setFocus(Qt.FocusReason.OtherFocusReason)
