#pragma once

// Copie como device_config.h e substitua somente os valores desta instalação.
// device_config.h está no .gitignore e não deve ser versionado.
constexpr char WIFI_SSID[] = "CHANGE_ME_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "CHANGE_ME_WIFI_PASSWORD";
constexpr char API_HOST[] = "192.168.1.100";  // IPv4 da FastAPI na rede local.
constexpr uint16_t API_PORT = 8000;
constexpr char API_PATH[] = "/ws/devices/safety";
constexpr char DEVICE_TOKEN[] = "CHANGE_ME_WITH_THE_API_DEVICE_TOKEN";
