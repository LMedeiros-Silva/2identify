"""Lightweight class-aware tracking for consecutive PPE detection batches."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from app.vision.ppe.types import DetectionBox, PpeDetection, PpeDetectionBatch


@dataclass(frozen=True, slots=True)
class PpeTrackSnapshot:
    """Immutable state of one track after processing an inference batch."""

    track_id: int
    detection: PpeDetection
    hit_count: int
    age_batches: int
    missed_batches: int
    confirmed: bool

    def __post_init__(self) -> None:
        if self.track_id <= 0:
            raise ValueError("track_id deve ser maior que zero")
        if not isinstance(self.detection, PpeDetection):
            raise ValueError("detection deve ser uma PpeDetection")
        if self.hit_count < 1 or self.age_batches < self.hit_count:
            raise ValueError("contadores do track são inválidos")
        if not 0 <= self.missed_batches < self.age_batches:
            raise ValueError("missed_batches deve estar dentro da idade do track")
        if not isinstance(self.confirmed, bool):
            raise ValueError("confirmed deve ser booleano")

    @property
    def is_visible(self) -> bool:
        """Return whether this track matched a detection in the current batch."""

        return self.missed_batches == 0


@dataclass(frozen=True, slots=True)
class PpeTrackingBatch:
    """Tracks retained after one raw detection batch."""

    tracks: tuple[PpeTrackSnapshot, ...]
    frame_width: int
    frame_height: int
    inference_milliseconds: float
    sequence_number: int

    def __post_init__(self) -> None:
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError("dimensões do tracking devem ser positivas")
        if (
            not isfinite(self.inference_milliseconds)
            or self.inference_milliseconds < 0
        ):
            raise ValueError("tempo de inferência deve ser finito e não negativo")
        if self.sequence_number <= 0:
            raise ValueError("sequence_number deve ser maior que zero")
        if any(not isinstance(item, PpeTrackSnapshot) for item in self.tracks):
            raise ValueError("tracks deve conter somente PpeTrackSnapshot")
        track_ids = {item.track_id for item in self.tracks}
        if len(track_ids) != len(self.tracks):
            raise ValueError("tracks não pode repetir track_id")

    @property
    def visible_tracks(self) -> tuple[PpeTrackSnapshot, ...]:
        return tuple(item for item in self.tracks if item.is_visible)

    @property
    def confirmed_visible_tracks(self) -> tuple[PpeTrackSnapshot, ...]:
        return tuple(
            item for item in self.tracks if item.is_visible and item.confirmed
        )


@dataclass(slots=True)
class _MutableTrack:
    track_id: int
    detection: PpeDetection
    hit_count: int = 1
    age_batches: int = 1
    missed_batches: int = 0


class PpeDetectionTracker:
    """Associate same-class boxes by IoU and retain identity through short gaps."""

    def __init__(
        self,
        *,
        iou_threshold: float,
        maximum_missed_batches: int,
        minimum_confirmation_hits: int,
    ) -> None:
        if not 0.0 < iou_threshold <= 1.0:
            raise ValueError("iou_threshold deve estar entre zero e um")
        if maximum_missed_batches < 0:
            raise ValueError("maximum_missed_batches não pode ser negativo")
        if minimum_confirmation_hits < 1:
            raise ValueError("minimum_confirmation_hits deve ser maior que zero")
        self._iou_threshold = iou_threshold
        self._maximum_missed_batches = maximum_missed_batches
        self._minimum_confirmation_hits = minimum_confirmation_hits
        self._tracks: dict[int, _MutableTrack] = {}
        self._next_track_id = 1
        self._sequence_number = 0

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)

    def reset(self) -> None:
        """Discard all identities when the camera or WorkSession changes."""

        self._tracks.clear()
        self._next_track_id = 1
        self._sequence_number = 0

    def update(self, batch: PpeDetectionBatch) -> PpeTrackingBatch:
        """Process one batch with deterministic one-to-one IoU association."""

        if not isinstance(batch, PpeDetectionBatch):
            raise ValueError("batch deve ser um PpeDetectionBatch")
        self._sequence_number += 1
        matches = self._associate(batch.detections)
        matched_detection_indexes = set(matches.values())

        for track_id, track in tuple(self._tracks.items()):
            track.age_batches += 1
            detection_index = matches.get(track_id)
            if detection_index is None:
                track.missed_batches += 1
                if track.missed_batches > self._maximum_missed_batches:
                    del self._tracks[track_id]
                continue
            track.detection = batch.detections[detection_index]
            track.hit_count += 1
            track.missed_batches = 0

        for detection_index, detection in enumerate(batch.detections):
            if detection_index in matched_detection_indexes:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = _MutableTrack(track_id, detection)

        snapshots = tuple(
            PpeTrackSnapshot(
                track_id=track.track_id,
                detection=track.detection,
                hit_count=track.hit_count,
                age_batches=track.age_batches,
                missed_batches=track.missed_batches,
                confirmed=track.hit_count >= self._minimum_confirmation_hits,
            )
            for track in sorted(self._tracks.values(), key=lambda item: item.track_id)
        )
        return PpeTrackingBatch(
            tracks=snapshots,
            frame_width=batch.frame_width,
            frame_height=batch.frame_height,
            inference_milliseconds=batch.inference_milliseconds,
            sequence_number=self._sequence_number,
        )

    def _associate(
        self,
        detections: tuple[PpeDetection, ...],
    ) -> dict[int, int]:
        candidates: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                if detection.class_name != track.detection.class_name:
                    continue
                overlap = _intersection_over_union(
                    track.detection.box,
                    detection.box,
                )
                if overlap >= self._iou_threshold:
                    candidates.append((-overlap, track_id, detection_index))

        matches: dict[int, int] = {}
        assigned_detections: set[int] = set()
        for _negative_overlap, track_id, detection_index in sorted(candidates):
            if track_id in matches or detection_index in assigned_detections:
                continue
            matches[track_id] = detection_index
            assigned_detections.add(detection_index)
        return matches


def _intersection_over_union(first: DetectionBox, second: DetectionBox) -> float:
    intersection_width = max(
        0.0,
        min(first.x2, second.x2) - max(first.x1, second.x1),
    )
    intersection_height = max(
        0.0,
        min(first.y2, second.y2) - max(first.y1, second.y1),
    )
    intersection = intersection_width * intersection_height
    first_area = max(0.0, first.x2 - first.x1) * max(
        0.0,
        first.y2 - first.y1,
    )
    second_area = max(0.0, second.x2 - second.x1) * max(
        0.0,
        second.y2 - second.y1,
    )
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0
