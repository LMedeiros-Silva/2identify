"""Face ID opens an API session (employee token) or nothing at all."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import numpy as np
import pytest

from app.api.client import OperatorApiClient
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod
from app.domain import CredentialAuthenticationResult, OperatorIdentity
from app.services.safety_state_service import SafetyStateSnapshot
from app.vision.face_auth.errors import (
    FaceAuthenticationUnavailableError,
    FaceNotRecognizedError,
)
from app.vision.face_auth.factory import build_face_authentication_pipeline
from tests.integration.test_application_controller import _setup_controller

STATION_TOKEN = "station-test-token-with-at-least-32-random-bytes"


def _employee_session() -> CredentialAuthenticationResult:
    return CredentialAuthenticationResult(
        operator_id=21, name="Ana Souza", access_token="employee-session-token"
    )


def test_face_identity_without_an_api_session_never_opens_the_operator(qtbot) -> None:
    """Defect: a local match opened a session with no token, so no alert reached the Admin."""

    login_window, session_context, controller = _setup_controller(qtbot)

    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )

    assert controller.main_window is None
    assert session_context.current is None
    assert login_window.isVisible()


def test_face_session_carries_the_employee_token_to_safety_reporting(qtbot) -> None:
    _login_window, session_context, controller = _setup_controller(qtbot)
    sent: list[tuple[SafetyStateSnapshot, str]] = []

    class SenderStub:
        def send_safety_state(self, snapshot, access_token):
            sent.append((snapshot, access_token))
            raise RuntimeError("not needed for this test")

    controller._safety_state_sender = SenderStub()
    controller._settings = AppSettings(_env_file=None)

    controller.handle_face_authentication(_employee_session())
    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    session = session_context.require_current()
    assert session.authentication_method is AuthenticationMethod.FACE_ID
    assert (session.operator_id, session.access_token) == (21, "employee-session-token")

    controller._handle_safety_state_snapshot(
        SafetyStateSnapshot(uuid4(), 41, None, datetime.now(UTC), ())
    )
    qtbot.waitUntil(lambda: bool(sent), timeout=2_000)
    assert sent[0][1] == "employee-session-token"
    controller.handle_logout()


def _client(handler) -> OperatorApiClient:
    return OperatorApiClient(
        "http://api.test",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )


def _probes() -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(7)
    return tuple(
        (vector / np.linalg.norm(vector)).astype(np.float32) for vector in rng.normal(size=(3, 128))
    )


def test_client_sends_station_credential_and_probes_and_reads_the_employee_session() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "access_token": "employee-session-token",
                "token_type": "bearer",
                "expires_in": 1800,
                "operator": {"id": 21, "name": "Ana Souza", "profile": "funcionario"},
            },
        )

    result = _client(handler).authenticate_face("opencv_sface_2021dec", _probes(), STATION_TOKEN)

    assert seen["path"] == "/auth/face"
    assert seen["authorization"] == f"Bearer {STATION_TOKEN}"
    body = seen["body"]
    assert set(body) == {"model_id", "probes"}  # the client never names the employee
    assert len(body["probes"]) == 3 and all(len(probe) == 128 for probe in body["probes"])
    assert (result.operator_id, result.name, result.access_token) == (
        21,
        "Ana Souza",
        "employee-session-token",
    )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, FaceNotRecognizedError),
        (403, FaceAuthenticationUnavailableError),
        (503, FaceAuthenticationUnavailableError),
        (422, FaceAuthenticationUnavailableError),
        (200, FaceAuthenticationUnavailableError),
    ],
)
def test_client_fails_closed_on_rejection_and_api_errors(status, error, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    probes = _probes()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "x"})

    with pytest.raises(error):
        _client(handler).authenticate_face("opencv_sface_2021dec", probes, STATION_TOKEN)
    logged = caplog.text + " ".join(str(record.__dict__) for record in caplog.records)
    assert STATION_TOKEN not in logged
    assert repr(float(probes[0][0])) not in logged


def test_client_reports_an_unreachable_api_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(FaceAuthenticationUnavailableError):
        _client(handler).authenticate_face("opencv_sface_2021dec", _probes(), STATION_TOKEN)


def test_face_id_is_unavailable_without_a_station_credential() -> None:
    with pytest.raises(FaceAuthenticationUnavailableError, match="OPERATOR_STATION_TOKEN"):
        build_face_authentication_pipeline(AppSettings(_env_file=None), authority=None)
