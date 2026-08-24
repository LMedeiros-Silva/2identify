from app.core.constants import PROJECT_ROOT


def test_esp32_firmware_preserves_the_electrical_and_transport_contract() -> None:
    source = (
        PROJECT_ROOT
        / "firmware"
        / "esp32_safety_signal"
        / "esp32_safety_signal.ino"
    ).read_text(encoding="utf-8")
    example_config = (
        PROJECT_ROOT
        / "firmware"
        / "esp32_safety_signal"
        / "device_config.example.h"
    ).read_text(encoding="utf-8")

    expected_pins = {
        "PIN_BUTTON = 13",
        "PIN_WHITE_1 = 14",
        "PIN_WHITE_2 = 27",
        "PIN_GREEN_1 = 26",
        "PIN_GREEN_2 = 25",
        "PIN_YELLOW_1 = 33",
        "PIN_YELLOW_2 = 32",
        "PIN_RED_1 = 21",
        "PIN_RED_2 = 22",
        "PIN_BUZZER = 23",
    }
    assert all(definition in source for definition in expected_pins)
    assert '#include "device_config.h"' in source
    assert 'API_PATH[] = "/ws/devices/safety"' in example_config
    assert "CHANGE_ME_WIFI_PASSWORD" in example_config
    assert "CHANGE_ME_WITH_THE_API_DEVICE_TOKEN" in example_config
    assert "Authorization: Bearer " in source
    assert "enableHeartbeat" in source
    assert "setDisconnected()" in source
    assert "DISCONNECTED_BLINK_INTERVAL_MS = 1000" in source
    assert "RED_BLINK_INTERVAL_MS = 500" in source
    assert "BUZZER_FREQUENCY_HZ = 1000" in source
    assert "delay(" not in source
