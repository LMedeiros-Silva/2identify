"""Identity value objects shared by vision and safety rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmployeeIdentity:
    """A recognized employee without coupling to a recognition implementation."""

    employee_id: int
    name: str
    confidence: float

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.employee_id <= 0:
            raise ValueError("employee_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name não pode ser vazio")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0.0 e 1.0")
        object.__setattr__(self, "name", normalized_name)

