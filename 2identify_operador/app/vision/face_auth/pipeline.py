"""Pure facial-authentication decision pipeline."""

from __future__ import annotations

from app.domain.auth import OperatorIdentity
from app.vision.face_auth.contracts import FaceDetector, FaceEncoder, FaceMatcher, LivenessVerifier
from app.vision.face_auth.types import (
    FacePipelineDecision,
    FacePipelineStatus,
    Frame,
    LivenessStatus,
)


class FaceAuthenticationPipeline:
    """Combine detection, liveness, encoding and stable template matching."""

    def __init__(
        self,
        detector: FaceDetector,
        encoder: FaceEncoder,
        liveness: LivenessVerifier,
        matcher: FaceMatcher,
        minimum_face_ratio: float,
        minimum_consecutive_matches: int,
    ) -> None:
        self._detector = detector
        self._encoder = encoder
        self._liveness = liveness
        self._matcher = matcher
        self._minimum_face_ratio = minimum_face_ratio
        self._minimum_consecutive_matches = minimum_consecutive_matches
        self._candidate_id: int | None = None
        self._candidate_count = 0

    def process(self, frame: Frame, timestamp: float) -> FacePipelineDecision:
        faces = self._detector.detect(frame)
        if not faces:
            self.reset()
            return FacePipelineDecision(
                FacePipelineStatus.WAITING_FACE,
                "Nenhum rosto detectado. Posicione-se em frente à câmera.",
            )
        if len(faces) > 1:
            self.reset()
            return FacePipelineDecision(
                FacePipelineStatus.MULTIPLE_FACES,
                "Mais de um rosto detectado. Apenas o operador deve permanecer na imagem.",
            )

        face = faces[0]
        frame_height, frame_width = frame.shape[:2]
        width_ratio = face.bounding_box.width / frame_width
        height_ratio = face.bounding_box.height / frame_height
        if min(width_ratio, height_ratio) < self._minimum_face_ratio:
            self._reset_match_candidate()
            return FacePipelineDecision(
                FacePipelineStatus.MOVE_CLOSER,
                "Aproxime-se da câmera para melhorar a identificação.",
            )

        liveness = self._liveness.observe(face, timestamp)
        if liveness.status is LivenessStatus.REJECTED:
            self._reset_match_candidate()
            return FacePipelineDecision(
                FacePipelineStatus.NOT_RECOGNIZED,
                liveness.message,
            )
        if liveness.status is LivenessStatus.PENDING:
            self._reset_match_candidate()
            return FacePipelineDecision(
                FacePipelineStatus.VERIFYING_LIVENESS,
                liveness.message,
            )

        embedding = self._encoder.encode(frame, face)
        match = self._matcher.match(embedding)
        if match is None:
            self._reset_match_candidate()
            return FacePipelineDecision(
                FacePipelineStatus.NOT_RECOGNIZED,
                "Rosto não reconhecido. Tente novamente ou use e-mail e senha.",
            )

        if self._candidate_id == match.template.operator_id:
            self._candidate_count += 1
        else:
            self._candidate_id = match.template.operator_id
            self._candidate_count = 1

        if self._candidate_count < self._minimum_consecutive_matches:
            return FacePipelineDecision(
                FacePipelineStatus.MATCHING,
                "Identidade encontrada. Confirmando correspondência...",
            )

        identity = OperatorIdentity(
            operator_id=match.template.operator_id,
            name=match.template.name,
            confidence=match.similarity,
            profile_photo_reference=match.template.profile_photo_reference,
        )
        return FacePipelineDecision(
            FacePipelineStatus.RECOGNIZED,
            "Identidade facial confirmada.",
            identity=identity,
        )

    def reset(self) -> None:
        self._liveness.reset()
        self._reset_match_candidate()

    def _reset_match_candidate(self) -> None:
        self._candidate_id = None
        self._candidate_count = 0

