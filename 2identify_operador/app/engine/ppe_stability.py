"""Framework-neutral temporal stabilization for PPE observations."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class PpeStabilityState(StrEnum):
    """Temporal decision for one model class required by an operation."""

    COLLECTING = "collecting"
    CONFIRMED_PRESENT = "confirmed_present"
    CONFIRMED_ABSENT = "confirmed_absent"
    UNSTABLE = "unstable"


@dataclass(frozen=True, slots=True)
class PpeStabilityDecision:
    """Evidence summary for one required PPE detection class."""

    detection_class: str
    state: PpeStabilityState
    observed_frames: int
    sample_count: int
    presence_ratio: float

    def __post_init__(self) -> None:
        normalized_class = self.detection_class.strip().casefold()
        if not normalized_class:
            raise ValueError("detection_class não pode ser vazia")
        if not isinstance(self.state, PpeStabilityState):
            raise ValueError("state deve ser um PpeStabilityState")
        if self.sample_count < 1:
            raise ValueError("sample_count deve ser maior que zero")
        if not 0 <= self.observed_frames <= self.sample_count:
            raise ValueError("observed_frames deve estar dentro da janela amostrada")
        if not isfinite(self.presence_ratio) or not 0.0 <= self.presence_ratio <= 1.0:
            raise ValueError("presence_ratio deve ser finito e estar entre 0 e 1")
        object.__setattr__(self, "detection_class", normalized_class)


@dataclass(frozen=True, slots=True)
class PpeStabilitySnapshot:
    """Immutable result of the current temporal observation window."""

    decisions: tuple[PpeStabilityDecision, ...]
    sample_count: int
    window_size: int

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size deve ser maior que zero")
        if not 1 <= self.sample_count <= self.window_size:
            raise ValueError("sample_count deve estar dentro do tamanho da janela")
        if any(not isinstance(item, PpeStabilityDecision) for item in self.decisions):
            raise ValueError("decisions deve conter somente PpeStabilityDecision")
        if any(item.sample_count != self.sample_count for item in self.decisions):
            raise ValueError("todas as decisões devem usar o sample_count do snapshot")
        detection_classes = {item.detection_class for item in self.decisions}
        if len(detection_classes) != len(self.decisions):
            raise ValueError("decisions não pode repetir detection_class")

    @property
    def all_confirmed_present(self) -> bool:
        """Return true only when at least one requirement is stably present."""

        return bool(self.decisions) and all(
            item.state is PpeStabilityState.CONFIRMED_PRESENT
            for item in self.decisions
        )

    def decision_for(self, detection_class: str) -> PpeStabilityDecision | None:
        """Find a decision using the same normalized class naming as inference."""

        normalized = detection_class.strip().casefold()
        return next(
            (
                item
                for item in self.decisions
                if item.detection_class == normalized
            ),
            None,
        )


class PpeStabilityEngine:
    """Aggregate recent frame observations without declaring work released."""

    def __init__(
        self,
        *,
        window_size: int,
        minimum_samples: int,
        present_ratio: float,
        absent_ratio: float,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size deve ser maior que zero")
        if not 1 <= minimum_samples <= window_size:
            raise ValueError(
                "minimum_samples deve estar entre um e o tamanho da janela"
            )
        if not 0.0 <= absent_ratio < present_ratio <= 1.0:
            raise ValueError(
                "os limiares devem respeitar 0 <= absent_ratio < present_ratio <= 1"
            )

        self._window_size = window_size
        self._minimum_samples = minimum_samples
        self._present_ratio = present_ratio
        self._absent_ratio = absent_ratio
        self._required_classes: tuple[str, ...] = ()
        self._observations: deque[frozenset[str]] = deque(maxlen=window_size)

    @property
    def sample_count(self) -> int:
        return len(self._observations)

    def reset(self, required_classes: Iterable[str] = ()) -> None:
        """Clear evidence and replace the operation-specific class set."""

        normalized_classes: list[str] = []
        seen: set[str] = set()
        for value in required_classes:
            normalized = value.strip().casefold()
            if not normalized:
                raise ValueError("required_classes não pode conter nomes vazios")
            if normalized not in seen:
                normalized_classes.append(normalized)
                seen.add(normalized)
        self._required_classes = tuple(normalized_classes)
        self._observations.clear()

    def observe(self, observed_classes: Iterable[str]) -> PpeStabilitySnapshot:
        """Add one frame and return decisions for the current rolling window."""

        observed = frozenset(
            normalized
            for item in observed_classes
            if (normalized := item.strip().casefold())
        )
        self._observations.append(observed)
        sample_count = len(self._observations)
        decisions = tuple(
            self._decide(detection_class, sample_count)
            for detection_class in self._required_classes
        )
        return PpeStabilitySnapshot(
            decisions=decisions,
            sample_count=sample_count,
            window_size=self._window_size,
        )

    def _decide(
        self,
        detection_class: str,
        sample_count: int,
    ) -> PpeStabilityDecision:
        observed_frames = sum(
            detection_class in observation for observation in self._observations
        )
        presence_ratio = observed_frames / sample_count
        if sample_count < self._minimum_samples:
            state = PpeStabilityState.COLLECTING
        elif presence_ratio >= self._present_ratio:
            state = PpeStabilityState.CONFIRMED_PRESENT
        elif presence_ratio <= self._absent_ratio:
            state = PpeStabilityState.CONFIRMED_ABSENT
        else:
            state = PpeStabilityState.UNSTABLE

        return PpeStabilityDecision(
            detection_class=detection_class,
            state=state,
            observed_frames=observed_frames,
            sample_count=sample_count,
            presence_ratio=presence_ratio,
        )
