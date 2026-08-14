"""Enroll local development templates from controlled operator photographs."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from app.core.config import AppEnvironment, AppSettings, get_settings
from app.core.constants import PROJECT_ROOT
from app.core.logging_config import configure_logging
from app.vision.face_auth.errors import FaceAuthenticationError
from app.vision.face_auth.opencv_models import SFaceEncoder, YuNetFaceDetector
from app.vision.face_auth.repository import JsonFaceTemplateRepository
from app.vision.face_auth.types import RegisteredFaceTemplate

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cadastra um template facial local somente para desenvolvimento.",
    )
    parser.add_argument("--operator-id", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--image",
        type=Path,
        action="append",
        required=True,
        help="imagem frontal controlada; repita o parâmetro para usar mais amostras",
    )
    parser.add_argument(
        "--profile-image",
        type=Path,
        help="foto exibida no login; usa a primeira --image quando omitida",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)

    if settings.app_environment is AppEnvironment.PRODUCTION:
        logger.error("local_face_enrollment_blocked_in_production")
        print("Cadastro local bloqueado: use o Admin/API no ambiente de produção.")
        return 2
    if not settings.face_auth_allow_local_authorization:
        print("Cadastro local desabilitado pela configuração desta instalação.")
        return 2
    if args.operator_id <= 0 or not args.name.strip():
        print("ID e nome do operador devem ser válidos.")
        return 2

    try:
        template = _create_template(
            settings=settings,
            operator_id=args.operator_id,
            name=args.name,
            image_paths=args.image,
            profile_image=args.profile_image,
        )
        repository = JsonFaceTemplateRepository(settings.face_auth_template_store_path)
        repository.upsert_template(template)
    except (FaceAuthenticationError, OSError, ValueError) as error:
        logger.error("local_face_enrollment_failed", extra={"reason": str(error)})
        print(f"Cadastro não concluído: {error}")
        return 1

    logger.info(
        "local_face_enrollment_completed",
        extra={"operator_id": template.operator_id, "samples": len(args.image)},
    )
    print(f"Biometria local cadastrada para {template.name} (ID {template.operator_id}).")
    return 0


def _create_template(
    settings: AppSettings,
    operator_id: int,
    name: str,
    image_paths: Sequence[Path],
    profile_image: Path | None,
) -> RegisteredFaceTemplate:
    resolved_samples = {path.expanduser().resolve() for path in image_paths}
    if len(resolved_samples) < 3:
        raise ValueError(
            "forneça ao menos três imagens distintas do operador para o cadastro"
        )

    detector = YuNetFaceDetector(
        settings.face_detector_model_path,
        settings.face_auth_detection_threshold,
    )
    encoder = SFaceEncoder(settings.face_recognition_model_path)
    embeddings = []

    for image_path in image_paths:
        resolved_path = image_path.expanduser().resolve()
        frame = cv2.imread(str(resolved_path))
        if frame is None:
            raise ValueError(f"não foi possível ler a imagem: {resolved_path}")
        faces = detector.detect(frame)
        if len(faces) != 1:
            raise ValueError(
                f"a imagem {resolved_path.name} deve conter exatamente um rosto; "
                f"detectados: {len(faces)}"
            )
        embeddings.append(encoder.encode(frame, faces[0]))

    averaged_embedding = np.mean(np.stack(embeddings), axis=0)
    norm = float(np.linalg.norm(averaged_embedding))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("não foi possível gerar um template facial válido")
    normalized_embedding = averaged_embedding / norm

    selected_profile = (profile_image or image_paths[0]).expanduser().resolve()
    profile_reference = _copy_profile_photo(selected_profile, operator_id)
    return RegisteredFaceTemplate(
        operator_id=operator_id,
        name=name.strip(),
        model_id=settings.face_auth_model_id,
        embedding=tuple(float(value) for value in normalized_embedding.tolist()),
        profile_photo_reference=profile_reference,
    )


def _copy_profile_photo(source: Path, operator_id: int) -> str:
    if not source.is_file():
        raise ValueError(f"foto de perfil não encontrada: {source}")
    suffix = source.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("a foto de perfil deve ser JPG, PNG ou WebP")

    directory = PROJECT_ROOT / "var" / "face_auth" / "profiles"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"operator_{operator_id}{suffix}"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return destination.relative_to(PROJECT_ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
