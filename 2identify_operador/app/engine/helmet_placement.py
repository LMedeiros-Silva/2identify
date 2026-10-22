"""Conservative, per-person helmet placement from PPE boxes and COCO pose."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from math import hypot

from app.vision.pose import CocoKeypoint, PersonPose, PoseDetectionBatch
from app.vision.ppe import PpeDetection, PpeDetectionBatch


class HelmetPlacement(StrEnum):
    NA_CABECA = "na_cabeca"
    NA_MAO = "na_mao"
    INDETERMINADO = "indeterminado"


class HelmetPendingReason(StrEnum):
    """Why the helmet is still INDETERMINADO, for the operator and the logs."""

    SEM_POSE = "sem_pose"
    SEM_REFERENCIA = "sem_referencia"
    SEM_CAPACETE = "sem_capacete"
    FORA_DA_CABECA = "fora_da_cabeca"
    ESTABILIZANDO = "estabilizando"
    OUTRA_PESSOA = "outra_pessoa"


@dataclass(frozen=True, slots=True)
class PersonHelmetPlacement:
    person_id: int
    placement: HelmetPlacement


@dataclass(frozen=True, slots=True)
class HelmetPlacementResult:
    camera_id: int | None
    people: tuple[PersonHelmetPlacement, ...]
    overall: HelmetPlacement
    pending_reason: HelmetPendingReason | None = None


def _point(person: PersonPose, name: CocoKeypoint) -> tuple[float, float] | None:
    point = person.keypoint(name)
    return (point.x, point.y) if point.confidence >= 0.5 else None


def person_geometry(person: PersonPose) -> tuple[tuple[float, float], float] | None:
    left = _point(person, CocoKeypoint.LEFT_SHOULDER)
    right = _point(person, CocoKeypoint.RIGHT_SHOULDER)
    face = [
        point
        for name in (
            CocoKeypoint.NOSE,
            CocoKeypoint.LEFT_EYE,
            CocoKeypoint.RIGHT_EYE,
            CocoKeypoint.LEFT_EAR,
            CocoKeypoint.RIGHT_EAR,
        )
        if (point := _point(person, name)) is not None
    ]
    if person.confidence < 0.5 or left is None or right is None or len(face) < 2:
        return None
    width = hypot(right[0] - left[0], right[1] - left[1])
    if width < 8:
        return None
    center = (sum(x for x, _ in face) / len(face), sum(y for _, y in face) / len(face))
    return center, width


def _candidate(detection: PpeDetection, person: PersonPose) -> tuple[HelmetPlacement, float] | None:
    geometry = person_geometry(person)
    if geometry is None:
        return None
    (head_x, head_y), width = geometry
    box = detection.box
    x, y = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
    # The face and shoulders supply a scale; no image-resolution-specific pixels.
    head_distance = hypot((x - head_x) / width, (y - (head_y - 0.35 * width)) / width)
    if head_distance <= 0.75:
        return HelmetPlacement.NA_CABECA, head_distance
    hands = [
        _point(person, CocoKeypoint.LEFT_WRIST),
        _point(person, CocoKeypoint.RIGHT_WRIST),
    ]
    hand_distance = min(
        (hypot(x - hand[0], y - hand[1]) / width for hand in hands if hand is not None),
        default=float("inf"),
    )
    if hand_distance <= 0.65:
        return HelmetPlacement.NA_MAO, hand_distance
    return None


def classify_helmet(detection: PpeDetection, person: PersonPose) -> HelmetPlacement:
    """Return UNKNOWN unless this person's reliable landmarks place the helmet."""
    candidate = _candidate(detection, person)
    return candidate[0] if candidate is not None else HelmetPlacement.INDETERMINADO


@dataclass(slots=True)
class _PersonTrack:
    person_id: int
    head: tuple[float, float]
    scale: float
    history: deque[HelmetPlacement] = field(default_factory=deque)
    missed: int = 0


class HelmetPlacementEngine:
    """Stabilize independent person observations within each camera generation.

    A placement is stable when at least ``stability_frames`` of the person's last
    ``window_frames`` observations agree and they make up ``present_ratio`` of that
    window. The defaults keep the strict form (N consecutive observations). A frame
    without helmet evidence is UNKNOWN: it counts against the ratio but does not erase
    the observations already collected, and a person whose landmarks drop out for up
    to ``maximum_missed_frames`` frames keeps that history.
    """

    def __init__(
        self,
        *,
        stability_frames: int = 3,
        window_frames: int | None = None,
        present_ratio: float = 1.0,
        maximum_missed_frames: int = 0,
    ) -> None:
        if stability_frames < 1:
            raise ValueError("stability_frames deve ser positivo")
        window = stability_frames if window_frames is None else window_frames
        if window < stability_frames:
            raise ValueError("window_frames deve ser maior ou igual a stability_frames")
        if not 0.0 < present_ratio <= 1.0:
            raise ValueError("present_ratio deve estar entre 0 e 1")
        if maximum_missed_frames < 0:
            raise ValueError("maximum_missed_frames não pode ser negativo")
        self._stability_frames = stability_frames
        self._window_frames = window
        self._present_ratio = present_ratio
        self._maximum_missed_frames = maximum_missed_frames
        self._tracks: dict[int | None, list[_PersonTrack]] = {}
        self._generations: dict[int | None, int] = {}
        self._next_id = 1

    def reset(self, camera_id: int | None = None) -> None:
        self._tracks.pop(camera_id, None)
        self._generations.pop(camera_id, None)

    def observe(
        self, ppe: PpeDetectionBatch, pose: PoseDetectionBatch | None
    ) -> HelmetPlacementResult:
        camera_id = ppe.camera_id
        unknown = HelmetPlacementResult(
            camera_id, (), HelmetPlacement.INDETERMINADO, HelmetPendingReason.SEM_POSE
        )
        if (
            pose is None
            or pose.camera_id != camera_id
            or pose.generation != ppe.generation
            or pose.frame_width != ppe.frame_width
            or pose.frame_height != ppe.frame_height
            or (
                ppe.captured_at is not None
                and pose.captured_at is not None
                and abs((ppe.captured_at - pose.captured_at).total_seconds()) > 1.0
            )
        ):
            self.reset(camera_id)
            return unknown
        if self._generations.get(camera_id) != ppe.generation:
            self.reset(camera_id)
            self._generations[camera_id] = ppe.generation

        tracks = self._tracks.setdefault(camera_id, [])
        observed: list[tuple[_PersonTrack, PersonPose]] = []
        available = tracks.copy()
        for person in pose.poses:
            geometry = person_geometry(person)
            if geometry is None:
                continue
            head, scale = geometry
            nearest = min(
                available,
                key=lambda item: hypot(head[0] - item.head[0], head[1] - item.head[1]) / scale,
                default=None,
            )
            if (
                nearest is not None
                and hypot(head[0] - nearest.head[0], head[1] - nearest.head[1]) <= scale
            ):
                track = nearest
                available.remove(track)
            else:
                track = _PersonTrack(
                    self._next_id, head, scale, deque(maxlen=self._window_frames)
                )
                self._next_id += 1
            track.head, track.scale, track.missed = head, scale, 0
            observed.append((track, person))
        # Landmarks of a known person may drop out for a few frames; keep the history.
        missed = []
        for track in available:
            track.missed += 1
            if track.missed <= self._maximum_missed_frames:
                track.history.append(HelmetPlacement.INDETERMINADO)
                missed.append(track)
        self._tracks[camera_id] = [track for track, _ in observed] + missed

        # A helmet is assigned only when one person's geometry wins clearly.
        placements = {track.person_id: HelmetPlacement.INDETERMINADO for track, _ in observed}
        for detection in ppe.detections:
            if detection.class_name != "capacete":
                continue
            candidates = sorted(
                (score, track.person_id, placement)
                for track, person in observed
                if (candidate := _candidate(detection, person)) is not None
                for placement, score in (candidate,)
            )
            if not candidates or (
                len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 0.2
            ):
                continue
            _, person_id, placement = candidates[0]
            prior = placements[person_id]
            if prior is not HelmetPlacement.NA_CABECA:
                placements[person_id] = placement

        people = []
        for track, _ in observed:
            track.history.append(placements[track.person_id])
            people.append(PersonHelmetPlacement(track.person_id, self._stable(track)))
        # A person not seen in this frame cannot confirm anything right now.
        people.extend(
            PersonHelmetPlacement(track.person_id, HelmetPlacement.INDETERMINADO)
            for track in missed
        )
        states = [person.placement for person in people]
        if HelmetPlacement.NA_MAO in states:
            overall = HelmetPlacement.NA_MAO
        elif states and all(state is HelmetPlacement.NA_CABECA for state in states):
            overall = HelmetPlacement.NA_CABECA
        else:
            overall = HelmetPlacement.INDETERMINADO
        reason = None
        if overall is HelmetPlacement.INDETERMINADO:
            reason = self._pending_reason(ppe, observed, placements, states)
        return HelmetPlacementResult(camera_id, tuple(people), overall, reason)

    @staticmethod
    def _pending_reason(
        ppe: PpeDetectionBatch,
        observed: list[tuple[_PersonTrack, PersonPose]],
        placements: dict[int, HelmetPlacement],
        states: list[HelmetPlacement],
    ) -> HelmetPendingReason:
        if not observed:
            return HelmetPendingReason.SEM_REFERENCIA
        if HelmetPlacement.NA_CABECA in states:
            return HelmetPendingReason.OUTRA_PESSOA
        if not any(item.class_name == "capacete" for item in ppe.detections):
            return HelmetPendingReason.SEM_CAPACETE
        if HelmetPlacement.NA_CABECA in placements.values():
            return HelmetPendingReason.ESTABILIZANDO
        return HelmetPendingReason.FORA_DA_CABECA

    def _stable(self, track: _PersonTrack) -> HelmetPlacement:
        history = track.history
        # NA_MAO is checked first so a helmet held in the hand is never read as worn.
        for placement in (HelmetPlacement.NA_MAO, HelmetPlacement.NA_CABECA):
            count = sum(item is placement for item in history)
            if count >= self._stability_frames and count / len(history) >= self._present_ratio:
                return placement
        return HelmetPlacement.INDETERMINADO
