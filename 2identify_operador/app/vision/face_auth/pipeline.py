"""Facial-authentication decision pipeline: live frames here, identity at the API."""

from __future__ import annotations

from app.vision.face_auth.contracts import (
    FaceDetector,
    FaceEncoder,
    FaceIdentityAuthority,
    LivenessVerifier,
)
from app.vision.face_auth.errors import FaceNotRecognizedError
from app.vision.face_auth.types import (
    Embedding,
    FacePipelineDecision,
    FacePipelineStatus,
    Frame,
    LivenessStatus,
)


class FaceAuthenticationPipeline:
    """Detect one live face, encode consecutive frames and let the API identify them.

    The station never decides who the person is: the API compares every probe with the
    templates enrolled in the Admin and returns the employee session, or rejects.
    """

    def __init__(
        self,
        detector: FaceDetector,
        encoder: FaceEncoder,
        liveness: LivenessVerifier,
        authority: FaceIdentityAuthority,
        model_id: str,
        minimum_face_ratio: float,
        minimum_consecutive_matches: int,
    ) -> None:
        self._detector = detector
        self._encoder = encoder
        self._liveness = liveness
        self._authority = authority
        self._model_id = model_id
        self._minimum_face_ratio = minimum_face_ratio
        self._minimum_consecutive_matches = minimum_consecutive_matches
        self._probes: list[Embedding] = []

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

        self._probes.append(self._encoder.encode(frame, face))
        if len(self._probes) < self._minimum_consecutive_matches:
            return FacePipelineDecision(
                FacePipelineStatus.MATCHING,
                "Rosto capturado. Confirmando identidade...",
            )

        probes = tuple(self._probes)
        self._reset_match_candidate()
        try:
            session = self._authority.authenticate(self._model_id, probes)
        except FaceNotRecognizedError:
            return FacePipelineDecision(
                FacePipelineStatus.NOT_RECOGNIZED,
                "Rosto não reconhecido. Tente novamente ou use e-mail e senha.",
            )
        return FacePipelineDecision(
            FacePipelineStatus.RECOGNIZED,
            "Identidade facial confirmada.",
            identity=session,
        )

    def reset(self) -> None:
        self._liveness.reset()
        self._reset_match_candidate()

    def _reset_match_candidate(self) -> None:
        # Probes must come from consecutive valid frames of the same live face.
        self._probes.clear()

