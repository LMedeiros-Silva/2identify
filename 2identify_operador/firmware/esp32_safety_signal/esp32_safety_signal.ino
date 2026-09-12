#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// Opcional: mantenha as credenciais em device_config.h (ignorado pelo Git).
// Ao colar somente este .ino no Arduino IDE, edite os valores abaixo.
#if __has_include("device_config.h")
#include "device_config.h"
#else
const char* WIFI_SSID = "SEU_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA";
const char* API_HOST = "192.168.0.100";  // IP do PC, nunca localhost.
const uint16_t API_PORT = 8000;
const char* API_PATH = "/ws/devices/safety";
const char* DEVICE_TOKEN = "SEU_DEVICE_TOKEN";
#endif

const int pinoVerde = 26;
const int pinoAmarelo = 33;
const int pinoVermelho = 21;
const int pinoBuzina = 23;
const int pinoBotao = 13;  // Reservado; nao controla o estado integrado.

const uint32_t RED_BLINK_MS = 500;
const uint32_t DISCONNECTED_BLINK_MS = 1000;
const uint32_t WIFI_RETRY_MS = 10000;
const uint32_t SERVER_TIMEOUT_MS = 30000;

enum class TowerState { DISCONNECTED, GREEN, YELLOW, RED };

WebSocketsClient webSocket;
TowerState towerState = TowerState::DISCONNECTED;
bool outputsInitialized = false;
bool blinkOn = true;
bool wifiWasConnected = false;
bool socketConnected = false;
bool stateReceived = false;
uint32_t lastBlinkMillis = 0;
uint32_t lastWifiAttemptMillis = 0;
uint32_t lastServerMessageMillis = 0;
String authorizationHeader;

// Prototipos explicitos para tipos definidos neste sketch.
void setTowerState(TowerState next);
const char* stateName(TowerState state);

void acionarRele(int pino, bool ligar) {
  digitalWrite(pino, ligar ? LOW : HIGH);  // ACTIVE LOW
}

const char* stateName(TowerState state) {
  switch (state) {
    case TowerState::GREEN: return "GREEN";
    case TowerState::YELLOW: return "YELLOW";
    case TowerState::RED: return "RED";
    default: return "DISCONNECTED";
  }
}

void setTowerState(TowerState next) {
  // Heartbeats repetidos nao reiniciam o pisca.
  if (outputsInitialized && towerState == next) return;
  towerState = next;
  outputsInitialized = true;
  blinkOn = true;
  lastBlinkMillis = millis();

  // Desliga todas as saidas antes de aplicar o novo estado.
  acionarRele(pinoVerde, false);
  acionarRele(pinoAmarelo, false);
  acionarRele(pinoVermelho, false);
  acionarRele(pinoBuzina, false);

  switch (next) {
    case TowerState::GREEN:
      acionarRele(pinoVerde, true);
      break;
    case TowerState::YELLOW:
    case TowerState::DISCONNECTED:
      acionarRele(pinoAmarelo, true);
      break;
    case TowerState::RED:
      acionarRele(pinoVermelho, true);
      acionarRele(pinoBuzina, true);
      break;
  }
  Serial.printf("[TOWER] %s\n", stateName(next));
}

void updateBlink() {
  uint32_t interval;
  if (towerState == TowerState::RED) interval = RED_BLINK_MS;
  else if (towerState == TowerState::DISCONNECTED) interval = DISCONNECTED_BLINK_MS;
  else return;

  const uint32_t now = millis();
  if (uint32_t(now - lastBlinkMillis) < interval) return;
  lastBlinkMillis = now;
  blinkOn = !blinkOn;
  if (towerState == TowerState::RED) {
    acionarRele(pinoVermelho, blinkOn);
    acionarRele(pinoBuzina, blinkOn);
  } else {
    acionarRele(pinoAmarelo, blinkOn);
  }
}

void rejectMessage() {
  stateReceived = false;
  setTowerState(TowerState::DISCONNECTED);
  Serial.println("[WS] Mensagem invalida; aguardando estado valido.");
}

void handleMessage(uint8_t* payload, size_t length) {
  if (!socketConnected || WiFi.status() != WL_CONNECTED) return;
  if (length == 0 || length > 1024) {
    rejectMessage();
    return;
  }
  JsonDocument document;
  const DeserializationError error = deserializeJson(
      document, payload, length, DeserializationOption::NestingLimit(4));
  if (error || !document["type"].is<const char*>() ||
      strcmp(document["type"].as<const char*>(), "safety_state") != 0 ||
      !document["schema_version"].is<int>() ||
      document["schema_version"].as<int>() != 1 ||
      !document["state"].is<const char*>()) {
    rejectMessage();
    return;
  }

  const char* state = document["state"].as<const char*>();
  TowerState next;
  if (strcmp(state, "GREEN") == 0) next = TowerState::GREEN;
  else if (strcmp(state, "YELLOW") == 0) next = TowerState::YELLOW;
  else if (strcmp(state, "RED") == 0) next = TowerState::RED;
  else {
    rejectMessage();
    return;
  }
  lastServerMessageMillis = millis();
  stateReceived = true;
  setTowerState(next);
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      socketConnected = true;
      stateReceived = false;
      lastServerMessageMillis = millis();  // Prazo para o primeiro snapshot.
      setTowerState(TowerState::DISCONNECTED);
      Serial.println("[WS] Conectado; aguardando estado da API.");
      break;
    case WStype_TEXT:
      handleMessage(payload, length);
      break;
    case WStype_DISCONNECTED:
    case WStype_ERROR:
      socketConnected = false;
      stateReceived = false;
      setTowerState(TowerState::DISCONNECTED);
      Serial.println("[WS] Desconectado.");
      break;
    case WStype_PING:
    case WStype_PONG:
      // A biblioteca responde automaticamente. PONG nao valida o cache da API.
      break;
    default:
      rejectMessage();  // Binarios/fragmentos nao fazem parte deste protocolo.
      break;
  }
}

void updateWifi() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected) {
    if (!wifiWasConnected) {
      Serial.print("[WIFI] Conectado: ");
      Serial.println(WiFi.localIP());
      Serial.println("[WS] Conectando...");
    }
    wifiWasConnected = true;
    return;
  }
  const bool mustDisconnectSocket = wifiWasConnected || socketConnected;
  wifiWasConnected = false;
  socketConnected = false;
  stateReceived = false;
  setTowerState(TowerState::DISCONNECTED);
  if (mustDisconnectSocket) {
    Serial.println("[WIFI] Desconectado.");
    webSocket.disconnect();
  }
  const uint32_t now = millis();
  if (uint32_t(now - lastWifiAttemptMillis) >= WIFI_RETRY_MS) {
    lastWifiAttemptMillis = now;
    Serial.println("[WIFI] Reconectando...");
    WiFi.reconnect();
  }
}

void checkServerTimeout() {
  if (socketConnected &&
      uint32_t(millis() - lastServerMessageMillis) >= SERVER_TIMEOUT_MS) {
    Serial.println("[WS] Timeout de mensagens da API.");
    socketConnected = false;
    stateReceived = false;
    setTowerState(TowerState::DISCONNECTED);
    webSocket.disconnect();  // O cliente tentara reconectar automaticamente.
  }
}

void setup() {
  Serial.begin(115200);
  const int pins[] = {pinoVerde, pinoAmarelo, pinoVermelho, pinoBuzina};
  for (int pin : pins) {
    digitalWrite(pin, HIGH);
    pinMode(pin, OUTPUT);
    acionarRele(pin, false);
  }
  pinMode(pinoBotao, INPUT_PULLUP);  // Intencionalmente sem leitura do botao.
  setTowerState(TowerState::DISCONNECTED);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  Serial.println("[WIFI] Conectando...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptMillis = millis();

  webSocket.begin(API_HOST, API_PORT, API_PATH);
  authorizationHeader = "Authorization: Bearer ";
  authorizationHeader += DEVICE_TOKEN;
  authorizationHeader += "\r\n";
  webSocket.setExtraHeaders(authorizationHeader.c_str());
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
  webSocket.enableHeartbeat(10000, 3000, 2);
}

void loop() {
  updateWifi();
  checkServerTimeout();
  webSocket.loop();
  checkServerTimeout();
  if (!socketConnected || !stateReceived || WiFi.status() != WL_CONNECTED) {
    setTowerState(TowerState::DISCONNECTED);
  }
  updateBlink();
}
