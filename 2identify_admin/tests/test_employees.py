"""Admin employee screen and API flow with a fake face capture."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic, sleep

import httpx
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QDialog

from app.api import AdminApiClient
from app.controllers.employees_controller import EmployeesController
from app.core.config import Settings
from app.core.session import AdminSessionContext
from app.domain import AdminAuthentication, Administrator
from app.domain.employees import (
    EmployeeDraft,
    EmployeeRecord,
    FaceTemplateDraft,
    FaceTemplateStatus,
)
from app.domain.operations import SectorOption
from app.services.errors import ApiUnavailableError
from app.ui.employees import EmployeesPage


def _record(employee_id: int = 7, *, active: bool = True) -> EmployeeRecord:
    now = datetime(2026, 9, 17, tzinfo=UTC)
    return EmployeeRecord(
        employee_id,
        "João",
        "MAT-7",
        1,
        "Usinagem",
        "Operador",
        "Manhã",
        active,
        now,
        now,
    )


def _template() -> FaceTemplateDraft:
    return FaceTemplateDraft("opencv_sface_2021dec", (1.0,) + (0.0,) * 127)


class _Dialog:
    def __init__(self, *_args) -> None:
        self.template = _template()

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


def _pump(qapp, condition) -> None:
    deadline = monotonic() + 3
    while not condition() and monotonic() < deadline:
        qapp.processEvents()
        sleep(0.01)
    assert condition()


def test_employee_screen_collects_existing_fields_and_face_capture(qapp) -> None:
    page = EmployeesPage(Settings(_env_file=None), face_dialog_factory=_Dialog)
    page.set_data((_record(),), (SectorOption(1, "Usinagem"),))
    page.select_employee(7)
    assert page.name.text() == "João"
    page.active.setChecked(False)
    page.face_button.click()
    spy = QSignalSpy(page.save_requested)
    page.save_button.click()
    assert spy.count() == 1
    draft, employee_id, face = spy.at(0)
    assert employee_id == 7
    assert draft.active is False
    assert draft.sector_id == 1
    assert face == _template()
    page.new_employee()
    assert page.name.text() == ""
    assert page.active.isChecked()
    page.close()


class _Service:
    def __init__(self) -> None:
        self.fail_face = True
        self.employee_ids: list[int | None] = []

    def load(self, token):
        assert token == "token"
        return (_record(),), (SectorOption(1, "Usinagem"),)

    def save_employee(self, token, draft, employee_id):
        assert token == "token"
        self.employee_ids.append(employee_id)
        return _record(8, active=draft.active)

    def save_face_template(self, token, employee_id, template):
        assert token == "token"
        assert employee_id == 8
        assert template == _template()
        if self.fail_face:
            raise ApiUnavailableError("API indisponível")
        return FaceTemplateStatus(8, template.model_id, datetime.now(UTC))


def test_api_failure_keeps_employee_and_face_retryable(qapp) -> None:
    page = EmployeesPage(Settings(_env_file=None), face_dialog_factory=_Dialog)
    session = AdminSessionContext()
    session.open(
        AdminAuthentication(
            Administrator(1, "Admin", "admin", "administrador"), "token", expires_in=60
        )
    )
    service = _Service()
    controller = EmployeesController(page, service, session, shutdown_timeout_ms=2000)
    controller.start()
    _pump(qapp, lambda: controller._worker is None and page.employee_list.count() == 1)
    page.new_employee()
    page.name.setText("João")
    page.registration.setText("MAT-8")
    page.face_button.click()
    page.save_button.click()
    _pump(qapp, lambda: controller._worker is None and bool(service.employee_ids))
    assert service.employee_ids == [None]
    assert page._editing_id == 8
    assert page._pending_face == _template()
    service.fail_face = False
    page.save_button.click()
    _pump(qapp, lambda: controller._worker is None and page._pending_face is None)
    assert service.employee_ids == [None, 8]
    assert "Face ID salvos" in page.feedback.text()
    assert controller.shutdown()
    page.close()


def test_employee_client_uses_admin_bearer_and_central_template_endpoint() -> None:
    requests: list[tuple[str, str]] = []
    employee = {
        "id": 8,
        "name": "João",
        "registration": "MAT-8",
        "sector_id": 1,
        "sector_name": "Usinagem",
        "role": "Operador",
        "shift": "Manhã",
        "active": True,
        "created_at": "2026-09-17T10:00:00Z",
        "updated_at": "2026-09-17T10:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer token"
        if request.url.path.endswith("/face-template"):
            assert request.method == "PUT"
            assert len(request.read()) > 0
            return httpx.Response(
                200,
                json={
                    "employee_id": 8,
                    "model_id": "opencv_sface_2021dec",
                    "enrolled_at": "2026-09-17T10:01:00Z",
                },
            )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [employee],
                    "total": 1,
                    "limit": 100,
                    "offset": 0,
                },
            )
        return httpx.Response(201, json=employee)

    with AdminApiClient(
        Settings(_env_file=None, API_URL="https://api.example.test"),
        transport=httpx.MockTransport(handler),
    ) as client:
        page = client.get_employees("token")
        saved = client.save_employee("token", EmployeeDraft("João", "MAT-8", 1))
        face = client.save_face_template("token", saved.id, _template())
    assert page.items[0].sector_name == "Usinagem"
    assert face.employee_id == 8
    assert requests == [
        ("GET", "/admin/employees"),
        ("POST", "/admin/employees"),
        ("PUT", "/admin/employees/8/face-template"),
    ]
