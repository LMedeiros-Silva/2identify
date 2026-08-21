from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from PySide6.QtCore import QObject, Signal

from app.api import AdminApiClient
from app.controllers import ApplicationController
from app.core.config import Settings


class TrackingRealtimeController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(self, session_context) -> None:
        super().__init__()
        self.session_context = session_context
        self.started = False
        self.shutdown_calls = 0
        self.session_was_present_at_shutdown = False

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        self.session_was_present_at_shutdown = self.session_context.current() is not None
        self.started = False
        return True


def settings() -> Settings:
    return Settings(_env_file=None, API_URL="https://api.example.test")  # type: ignore[call-arg]


def wait_until(qapp, predicate: Callable[[], bool], timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("A condição Qt não foi atendida dentro do prazo.")


def test_dashboard_unauthorized_returns_to_login(qapp) -> None:
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        if request.url.path == "/auth/admin/login":
            return httpx.Response(
                200,
                json={
                    "access_token": "token",
                    "token_type": "bearer",
                    "expires_in": 60,
                    "administrator": {
                        "id": 1,
                        "name": "Admin",
                        "username": "admin",
                        "profile": "administrador",
                    },
                },
            )
        if request.url.path == "/admin/me":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Admin",
                    "username": "admin",
                    "profile": "administrador",
                },
            )
        return httpx.Response(401, json={"detail": "expired"})

    client = AdminApiClient(settings(), transport=httpx.MockTransport(handler))
    controller = ApplicationController(qapp, settings(), client)
    controller.start()
    controller.login_window.campo_usuario.setText("admin")
    controller.login_window.campo_senha.setText("senha-segura")
    controller.login_window.botao_entrar.click()

    wait_until(
        qapp,
        lambda: "/admin/dashboard/summary" in observed_paths
        and controller.main_window is None,
    )

    assert controller.login_window.isVisible()
    assert "sessão expirou" in controller.login_window.mensagem_erro.text().lower()
    controller.shutdown()
    assert not controller._about_to_quit_connected  # type: ignore[attr-defined]
    controller.login_window.close()


def test_offline_login_stays_recoverable_and_clears_password(qapp) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = AdminApiClient(settings(), transport=httpx.MockTransport(handler))
    controller = ApplicationController(qapp, settings(), client)
    controller.start()
    controller.login_window.campo_usuario.setText("admin")
    controller.login_window.campo_senha.setText("segredo-temporario")
    controller.login_window.botao_entrar.click()

    wait_until(
        qapp,
        lambda: controller.login_window.mensagem_erro.isVisible(),
    )

    assert controller.login_window.botao_entrar.isEnabled()
    assert controller.login_window.campo_senha.text() == ""
    assert "API" in controller.login_window.mensagem_erro.text()
    controller.shutdown()
    controller.login_window.close()


def test_realtime_starts_after_login_and_stops_before_session_is_cleared(qapp) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/admin/login":
            return httpx.Response(
                200,
                json={
                    "access_token": "token",
                    "token_type": "bearer",
                    "expires_in": 60,
                    "administrator": {
                        "id": 1,
                        "name": "Admin",
                        "username": "admin",
                        "profile": "administrador",
                    },
                },
            )
        if request.url.path == "/admin/me":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Admin",
                    "username": "admin",
                    "profile": "administrador",
                },
            )
        return httpx.Response(
            200,
            json={
                "active_employees": 3,
                "ppe_assignments": 12,
                "delivered_ppe": 9,
                "ppe_delivery_percentage": 75.0,
                "alerts": 0,
                "critical_alerts": 0,
                "generated_at": "2026-08-20T12:00:00Z",
            },
        )

    realtime_instances: list[TrackingRealtimeController] = []

    def realtime_factory(_settings, context, _service, _view, _refresh):
        instance = TrackingRealtimeController(context)
        realtime_instances.append(instance)
        return instance

    client = AdminApiClient(settings(), transport=httpx.MockTransport(handler))
    controller = ApplicationController(
        qapp,
        settings(),
        client,
        realtime_controller_factory=realtime_factory,
    )
    controller.start()
    controller.login_window.campo_usuario.setText("admin")
    controller.login_window.campo_senha.setText("senha-segura")
    controller.login_window.botao_entrar.click()

    wait_until(
        qapp,
        lambda: len(realtime_instances) == 1
        and realtime_instances[0].started
        and controller.dashboard_controller is not None
        and controller.dashboard_controller._worker is None,  # type: ignore[attr-defined]
    )

    realtime = realtime_instances[0]
    controller.logout()

    assert realtime.shutdown_calls == 1
    assert realtime.session_was_present_at_shutdown
    assert realtime.session_context.current() is None
    assert controller.main_window is None
    assert controller.login_window.isVisible()
    controller.shutdown()
    controller.login_window.close()
