import json

import pytest

from app.vision.face_auth.errors import FaceAuthenticationUnavailableError
from app.vision.face_auth.repository import JsonFaceTemplateRepository
from app.vision.face_auth.types import RegisteredFaceTemplate


def _template(operator_id: int = 7) -> RegisteredFaceTemplate:
    return RegisteredFaceTemplate(
        operator_id=operator_id,
        name="Marina Costa",
        model_id="test-model",
        embedding=tuple(float(index) for index in range(128)),
        profile_photo_reference="var/face_auth/profiles/operator_7.jpg",
    )


def test_repository_round_trip_and_upsert(tmp_path) -> None:
    repository = JsonFaceTemplateRepository(tmp_path / "operators.json")
    repository.upsert_template(_template())
    repository.upsert_template(_template(operator_id=9))

    templates = repository.load_templates("test-model")

    assert [template.operator_id for template in templates] == [7, 9]
    assert templates[0].name == "Marina Costa"
    assert "embedding" not in repr(templates[0])


def test_repository_rejects_wrong_model(tmp_path) -> None:
    path = tmp_path / "operators.json"
    path.write_text(
        json.dumps({"version": 1, "model_id": "old-model", "operators": []}),
        encoding="utf-8",
    )

    with pytest.raises(FaceAuthenticationUnavailableError, match="outro modelo"):
        JsonFaceTemplateRepository(path).load_templates("new-model")

