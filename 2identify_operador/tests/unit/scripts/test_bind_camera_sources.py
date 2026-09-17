from __future__ import annotations

import pytest

from scripts.bind_camera_sources import build_bindings, main, write_bindings


def test_binds_real_ids_without_printing_local_sources(tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CAMERA_STAGED_FRESA_1=rtsp://camera.local/live\nOTHER_SETTING=kept\n",
        encoding="utf-8",
    )
    assert main(
        [
            "--env-file", str(env_file),
            "--camera", "FRESA_1=12",
            "--usb", "13=0",
        ]
    ) == 0
    content = env_file.read_text(encoding="utf-8")
    assert "CAMERA_SOURCE_12=rtsp://camera.local/live" in content
    assert "CAMERA_SOURCE_13=0" in content
    assert "OTHER_SETTING=kept" in content
    assert capsys.readouterr().out.splitlines() == [
        "CAMERA_SOURCE_12=CONFIGURADO",
        "CAMERA_SOURCE_13=CONFIGURADO",
    ]


def test_rejects_duplicate_id_and_accidental_replacement(tmp_path) -> None:
    with pytest.raises(ValueError, match="camera_id repetido"):
        build_bindings(
            {"CAMERA_STAGED_FRESA_1": "rtsp://camera.local/live"},
            ["FRESA_1=12"],
            ["12=0"],
        )
    env_file = tmp_path / ".env"
    env_file.write_text("CAMERA_SOURCE_12=rtsp://old.local/live\n", encoding="utf-8")
    with pytest.raises(ValueError, match="já existe"):
        write_bindings(env_file, {12: "rtsp://new.local/live"}, replace=False)
    assert env_file.read_text(encoding="utf-8") == "CAMERA_SOURCE_12=rtsp://old.local/live\n"
