#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WebSocketsClient.h>

#include "device_config.h"

constexpr uint8_t PIN_BUTTON = 13;
constexpr uint8_t PIN_WHITE_1 = 14;
constexpr uint8_t PIN_WHITE_2 = 27;
constexpr uint8_t PIN_GREEN_1 = 26;
constexpr uint8_t PIN_GREEN_2 = 25;
constexpr uint8_t PIN_YELLOW_1 = 33;
constexpr uint8_t PIN_YELLOW_2 = 32;
constexpr uint8_t PIN_RED_1 = 21;
constexpr uint8_t PIN_RED_2 = 22;
constexpr uint8_t PIN_BUZZER = 23;

constexpr unsigned long RED_BLINK_INTERVAL_MS = 500;
constexpr unsigned long DISCONNECTED_BLINK_INTERVAL_MS = 1000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint16_t BUZZER_FREQUENCY_HZ = 1000;

enum class DeviceMode : uint8_t {
  GREEN,
  YELLOW,
  RED,
  DISCONNECTED,
};

WebSocketsClient webSocket;
DeviceMode currentMode = DeviceMode::DISCONNECTED;
bool blinkOutputOn = true;
bool socketConnected = false;
bool stateReceived = false;
unsigned long lastBlinkAt = 0;
unsigned long lastWifiAttemptAt = 0;
String authorizationHeader;

void setPair(uint8_t firstPin, uint8_t secondPin, bool enabled) {
  digitalWrite(firstPin, enabled ? HIGH : LOW);
  digitalWrite(secondPin, enabled ? HIGH : LOW);
}

void keepWhiteOn() {
  setPair(PIN_WHITE_1, PIN_WHITE_2, true);
}

void clearSafetyOutputs() {
  setPair(PIN_GREEN_1, PIN_GREEN_2, false);
  setPair(PIN_YELLOW_1, PIN_YELLOW_2, false);
  setPair(PIN_RED_1, PIN_RED_2, false);
  noTone(PIN_BUZZER);
}

void beginMode(DeviceMode mode) {
  currentMode = mode;
  blinkOutputOn = true;
  lastBlinkAt = millis();
  keepWhiteOn();
  clearSafetyOutputs();
}

void setGreen() {
  beginMode(DeviceMode::GREEN);
  setPair(PIN_GREEN_1, PIN_GREEN_2, true);
}

void setYellow() {
  beginMode(DeviceMode::YELLOW);
  setPair(PIN_YELLOW_1, PIN_YELLOW_2, true);
}

void setRed() {
  beginMode(DeviceMode::RED);
  setPair(PIN_RED_1, PIN_RED_2, true);
  tone(PIN_BUZZER, BUZZER_FREQUENCY_HZ);
}

void setDisconnected() {
  beginMode(DeviceMode::DISCONNECTED);
  setPair(PIN_YELLOW_1, PIN_YELLOW_2, true);
}

void updateBlink() {
  keepWhiteOn();
  const unsigned long now = millis();
  unsigned long interval = 0;

  if (currentMode == DeviceMode::RED) {
    interval = RED_BLINK_INTERVAL_MS;
  } else if (currentMode == DeviceMode::DISCONNECTED) {
    interval = DISCONNECTED_BLINK_INTERVAL_MS;
  } else {
    return;
  }

  if (now - lastBlinkAt < interval) {
    return;
  }

  lastBlinkAt = now;
  blinkOutputOn = !blinkOutputOn;
  if (currentMode == DeviceMode::RED) {
    setPair(PIN_RED_1, PIN_RED_2, blinkOutputOn);
    if (blinkOutputOn) {
      tone(PIN_BUZZER, BUZZER_FREQUENCY_HZ);
    } else {
      noTone(PIN_BUZZER);
    }
  } else {
    setPair(PIN_YELLOW_1, PIN_YELLOW_2, blinkOutputOn);
    noTone(PIN_BUZZER);
  }
}

void applySafetyState(const char* state) {
  if (strcmp(state, "GREEN") == 0) {
    setGreen();
  } else if (strcmp(state, "YELLOW") == 0) {
    setYellow();
  } else if (strcmp(state, "RED") == 0) {
    setRed();
  } else {
    Serial.printf("Estado de segurança desconhecido: %s\n", state);
    setDisconnected();
    stateReceived = false;
    return;
  }
  stateReceived = true;
}

void handleWebSocketMessage(uint8_t* payload, size_t length) {
  JsonDocument document;
  const DeserializationError error = deserializeJson(document, payload, length);
  if (error) {
    Serial.printf("Mensagem JSON inválida: %s\n", error.c_str());
    return;
  }

  const char* type = document["type"] | "";
  const int schemaVersion = document["schema_version"] | 0;
  const char* state = document["state"] | "";
  if (strcmp(type, "safety_state") != 0 || schemaVersion != 1) {
    Serial.println("Mensagem WebSocket incompatível ignorada.");
    return;
  }

  Serial.printf(
      "Estado recebido: %s; motivo: %s; condições: %d\n",
      state,
      document["reason"] | "SAFE",
      document["active_conditions"] | 0);
  applySafetyState(state);
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      socketConnected = true;
      stateReceived = false;
      setDisconnected();
      Serial.println("WebSocket conectado; aguardando estado atual da API.");
      break;
    case WStype_TEXT:
      handleWebSocketMessage(payload, length);
      break;
    case WStype_DISCONNECTED:
    case WStype_ERROR:
      socketConnected = false;
      stateReceived = false;
      setDisconnected();
      Serial.println("WebSocket desconectado; sinalizador em modo de falha.");
      break;
    case WStype_PING:
    case WStype_PONG:
    case WStype_BIN:
    case WStype_FRAGMENT_TEXT_START:
    case WStype_FRAGMENT_BIN_START:
    case WStype_FRAGMENT:
    case WStype_FRAGMENT_FIN:
      break;
  }
}

void beginWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptAt = millis();
}

void updateWifiConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (currentMode != DeviceMode::DISCONNECTED) {
    setDisconnected();
  }
  socketConnected = false;
  stateReceived = false;

  const unsigned long now = millis();
  if (now - lastWifiAttemptAt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }
  lastWifiAttemptAt = now;
  Serial.println("Tentando reconectar ao Wi-Fi...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void configurePins() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_WHITE_1, OUTPUT);
  pinMode(PIN_WHITE_2, OUTPUT);
  pinMode(PIN_GREEN_1, OUTPUT);
  pinMode(PIN_GREEN_2, OUTPUT);
  pinMode(PIN_YELLOW_1, OUTPUT);
  pinMode(PIN_YELLOW_2, OUTPUT);
  pinMode(PIN_RED_1, OUTPUT);
  pinMode(PIN_RED_2, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
}

void setup() {
  Serial.begin(115200);
  configurePins();
  setDisconnected();
  beginWifi();

  authorizationHeader = "Authorization: Bearer ";
  authorizationHeader += DEVICE_TOKEN;
  authorizationHeader += "\r\n";
  webSocket.setExtraHeaders(authorizationHeader.c_str());
  webSocket.begin(API_HOST, API_PORT, API_PATH);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
  webSocket.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  updateWifiConnection();
  webSocket.loop();

  if (!socketConnected || !stateReceived || WiFi.status() != WL_CONNECTED) {
    if (currentMode != DeviceMode::DISCONNECTED) {
      setDisconnected();
    }
  }
  updateBlink();
}
