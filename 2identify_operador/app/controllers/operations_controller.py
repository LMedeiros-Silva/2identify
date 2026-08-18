"""Controller for loading operation data into the authenticated workspace."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.domain.operation import Operation
from app.services.manual_service import ManualService, ManualServiceError
from app.services.operation_service import OperationService, OperationServiceError
from app.ui.operations import OperationsPage, OperationsPageState

logger = logging.getLogger(__name__)


class OperationsController(QObject):
    """Coordinate the operation use case without coupling the page to a provider."""

    risk_area_requested = Signal(object)
    safety_verification_requested = Signal(object)

    def __init__(
        self,
        service: OperationService,
        page: OperationsPage,
        source_notice: str | None = None,
        manual_service: ManualService | None = None,
    ) -> None:
        super().__init__(page)
        self._service = service
        self._page = page
        self._source_notice = source_notice
        self._manual_service = manual_service
        self._operations_by_id: dict[int, Operation] = {}
        self._page.operation_selected.connect(self.select_operation)
        self._page.manual_requested.connect(self.open_manual)
        self._page.risk_area_requested.connect(self.request_risk_area)
        self._page.safety_verification_requested.connect(
            self.request_safety_verification
        )

    @Slot()
    def load_operations(self) -> None:
        """Load the configured source and map safe outcomes to view states."""

        self._operations_by_id.clear()
        self._page.set_list_state(OperationsPageState.LOADING)
        try:
            operations = self._service.list_available_operations()
        except OperationServiceError:
            logger.exception("operation_list_load_failed")
            self._page.set_list_state(
                OperationsPageState.ERROR,
                "Não foi possível consultar as operações. Tente novamente mais tarde.",
            )
            return

        self._operations_by_id = {
            operation.operation_id: operation for operation in operations
        }
        self._page.set_operations(operations, source_notice=self._source_notice)

    @Slot(int)
    def select_operation(self, operation_id: int) -> None:
        """Resolve a list intent against the loaded snapshot and update the view."""

        operation = self._operations_by_id.get(operation_id)
        if operation is None:
            logger.warning(
                "operation_selection_ignored_unknown_id",
                extra={"operation_id": operation_id},
            )
            return

        self._page.show_operation_details(operation)
        logger.info("operation_selected", extra={"operation_id": operation.operation_id})

    @Slot(int)
    def open_manual(self, operation_id: int) -> None:
        """Open the selected operation manual through the configured safe service."""

        operation = self._operations_by_id.get(operation_id)
        if operation is None or self._page.selected_operation_id != operation_id:
            logger.warning(
                "operation_manual_request_ignored_unknown_selection",
                extra={"operation_id": operation_id},
            )
            return
        if operation.manual is None:
            logger.warning(
                "operation_manual_request_ignored_not_configured",
                extra={"operation_id": operation_id},
            )
            return
        if self._manual_service is None:
            logger.error(
                "operation_manual_service_not_configured",
                extra={"operation_id": operation_id},
            )
            self._page.show_manual_error("O serviço de manuais não está configurado.")
            return

        try:
            self._manual_service.open_manual(operation.manual)
        except ManualServiceError:
            logger.exception(
                "operation_manual_open_failed",
                extra={"operation_id": operation_id},
            )
            self._page.show_manual_error(
                "Não foi possível abrir o manual PDF desta operação."
            )
            return

        logger.info("operation_manual_opened", extra={"operation_id": operation_id})

    @Slot(int)
    def request_risk_area(self, operation_id: int) -> None:
        """Validate and present configured risk-area geometry."""

        operation = self._operations_by_id.get(operation_id)
        if operation is None or self._page.selected_operation_id != operation_id:
            logger.warning(
                "risk_area_request_ignored_unknown_selection",
                extra={"operation_id": operation_id},
            )
            return
        if operation.risk_area is None:
            logger.warning(
                "risk_area_request_ignored_not_configured",
                extra={"operation_id": operation_id},
            )
            return
        if operation.risk_area.geometry is None:
            logger.warning(
                "risk_area_request_ignored_geometry_not_configured",
                extra={"operation_id": operation_id},
            )
            self._page.show_risk_area_unavailable()
            return

        self._page.show_risk_area(operation.risk_area)
        self.risk_area_requested.emit(operation.risk_area)
        logger.info(
            "risk_area_visualization_requested",
            extra={
                "operation_id": operation_id,
                "risk_area_id": operation.risk_area.risk_area_id,
            },
        )

    @Slot(int)
    def request_safety_verification(self, operation_id: int) -> None:
        """Validate selection and forward a non-starting verification intent."""

        operation = self._operations_by_id.get(operation_id)
        if operation is None or self._page.selected_operation_id != operation_id:
            logger.warning(
                "safety_verification_request_ignored_unknown_selection",
                extra={"operation_id": operation_id},
            )
            return
        if not operation.active:
            logger.warning(
                "safety_verification_request_ignored_inactive_operation",
                extra={"operation_id": operation_id},
            )
            return

        self.safety_verification_requested.emit(operation)
        logger.info(
            "safety_verification_page_requested",
            extra={"operation_id": operation_id},
        )
