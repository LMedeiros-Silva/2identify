"""Threads de trabalho para manter o event loop da interface responsivo."""

from app.workers.admin_workers import (
    AdminAlertActionWorker,
    AdminAlertsListWorker,
    AdminLoginWorker,
    AdminOperationsLoadWorker,
    AdminSessionValidationWorker,
    CameraFrameWorker,
    CameraSaveWorker,
    DashboardSummaryWorker,
    OperationSaveWorker,
    RiskAreaSaveWorker,
)

__all__ = [
    "AdminAlertActionWorker",
    "AdminAlertsListWorker",
    "AdminLoginWorker",
    "AdminSessionValidationWorker",
    "AdminOperationsLoadWorker",
    "CameraFrameWorker",
    "CameraSaveWorker",
    "DashboardSummaryWorker",
    "OperationSaveWorker",
    "RiskAreaSaveWorker",
]
