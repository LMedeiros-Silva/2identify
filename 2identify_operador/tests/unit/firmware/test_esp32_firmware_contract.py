from app.core.constants import PROJECT_ROOT


def test_esp32_firmware_preserves_the_electrical_and_transport_contract() -> None:
    source = (
        PROJECT_ROOT / "firmware" / "esp32_safety_signal" / "esp32_safety_signal.ino"
    ).read_text(encoding="utf-8")
    example_config = (
        PROJECT_ROOT / "firmware" / "esp32_safety_signal" / "device_config.example.h"
    ).read_text(encoding="utf-8")

    expected_pins = {
        "pinoBotao = 13",
        "pinoVerde = 26",
        "pinoAmarelo = 33",
        "pinoVermelho = 21",
        "pinoBuzina = 23",
    }
    assert all(definition in source for definition in expected_pins)
    assert '#include "device_config.h"' in source
    assert 'API_PATH[] = "/ws/devices/safety"' in example_config
    assert "CHANGE_ME_WIFI_PASSWORD" in example_config
    assert "CHANGE_ME_WITH_THE_API_DEVICE_TOKEN" in example_config
    assert "Authorization: Bearer " in source
    assert "enableHeartbeat" in source
    assert "setTowerState(TowerState::DISCONNECTED)" in source
    assert "DISCONNECTED_BLINK_MS = 1000" in source
    assert "RED_BLINK_MS = 500" in source
    assert "SERVER_TIMEOUT_MS = 30000" in source
    assert "ligar ? LOW : HIGH" in source
    assert "lastServerMessageMillis" in source
    assert "digitalRead(" not in source
    assert "tone(" not in source
    assert "delay(" not in source
