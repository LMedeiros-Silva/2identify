from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AdminCredentials:
    """Credenciais efêmeras usadas somente durante a autenticação."""

    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        username = self.username.strip()
        if not username:
            raise ValueError("O usuário é obrigatório.")
        if not self.password:
            raise ValueError("A senha é obrigatória.")
        object.__setattr__(self, "username", username)


@dataclass(frozen=True, slots=True)
class Administrator:
    id: int
    name: str
    username: str
    profile: str

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("O identificador do administrador é inválido.")
        if not self.name.strip():
            raise ValueError("O nome do administrador é obrigatório.")
        if not self.username.strip():
            raise ValueError("O usuário do administrador é obrigatório.")
        if self.profile != "administrador":
            raise ValueError("O perfil autenticado não é administrador.")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "username", self.username.strip())


@dataclass(frozen=True, slots=True)
class AdminAuthentication:
    administrator: Administrator
    access_token: str = field(repr=False)
    token_type: str = "bearer"
    expires_in: int = 0

    def __post_init__(self) -> None:
        token = self.access_token.strip()
        if not token:
            raise ValueError("O token de acesso está vazio.")
        if self.token_type.lower() != "bearer":
            raise ValueError("O tipo de token retornado pela API não é suportado.")
        if self.expires_in <= 0:
            raise ValueError("A duração do token é inválida.")
        object.__setattr__(self, "access_token", token)
        object.__setattr__(self, "token_type", "bearer")


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    active_employees: int
    ppe_assignments: int
    delivered_ppe: int
    ppe_delivery_percentage: float
    alerts: int
    critical_alerts: int
    generated_at: datetime

    def __post_init__(self) -> None:
        counts = (
            self.active_employees,
            self.ppe_assignments,
            self.delivered_ppe,
            self.alerts,
            self.critical_alerts,
        )
        if any(value < 0 for value in counts):
            raise ValueError("Os indicadores do dashboard não podem ser negativos.")
        if self.delivered_ppe > self.ppe_assignments:
            raise ValueError("EPIs entregues não podem exceder as associações.")
        if self.critical_alerts > self.alerts:
            raise ValueError("Alertas críticos não podem exceder o total de alertas.")
        if not 0 <= self.ppe_delivery_percentage <= 100:
            raise ValueError("O percentual de entrega de EPIs é inválido.")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at deve conter fuso horário.")
