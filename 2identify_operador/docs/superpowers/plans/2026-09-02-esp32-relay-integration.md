# ESP32 active-low safety tower implementation plan

> **For agentic workers:** Execute inline using superpowers:executing-plans and test-driven-development. Preserve the unrelated in-progress PPE changes.

**Goal:** Drive GPIO 26/33/21/23 active-low relays from the existing authenticated safety WebSocket, including restart recovery and fail-safe communication loss.

**Architecture:** Reuse AlertEngine, alert ingestion, persisted `alertas`, SafetyStateAggregator and the existing realtime broker. The database alert lifecycle is authoritative; a small aggregation reads non-closed alerts and broadcasts only changes. The existing Operator snapshot endpoint remains available for PPE realtime but must not override persisted alert state. The firmware only interprets GREEN/YELLOW/RED and implements DISCONNECTED locally.

**Tech stack:** FastAPI, SQLAlchemy, PySide6, pytest, ESP32 Arduino Core, WebSockets (Links2004), ArduinoJson 7.

**Spec:** User request in `C:/Users/gokga/.codex/attachments/619efaa1-1999-4f55-a74f-45beb33bae44/pasted-text.txt`.

## Constraints

- No second AlertEngine, MQTT, polling, direct database access from desktops or hardware.
- Retain `/ws/devices/safety` and `SAFETY_DEVICE_TOKEN` authentication.
- `warning` / persisted `aviso` => YELLOW; `critical` / `critico` => RED. `nao_lido` and `lido` remain active; `encerrado` is inactive.
- Automatic resolution uses the existing closure columns with no administrator actor. Confirmation alone does not resolve. A closed event must never reopen on an old retry.
- No real credentials, images or biometric data in source or logs; use placeholders only.
- Retain current Admin realtime envelope compatibility. Do not modify detection logic.
- GPIO 13 is configured but has no production control. GPIO 26/33/21/23 use LOW=on, HIGH=off. Boot disconnected, red/buzzer blink 500 ms, disconnected yellow 1000 ms, valid application messages timeout after 30 seconds.

## Task 1: Persisted aggregation and reconnect

Files: API `services/safety_state.py`, `repositories/safety_alert_repository.py`, `api/dependencies.py`, `api/routes/device_safety.py`, `api/routes/operator_safety_state.py`, `schemas/safety_state.py`, `tests/test_safety_state.py`.

- [x] Write parameterized aggregation tests for no alerts, warning, critical, mixed severity, partial/all resolution and failure invalidating a cached GREEN.
- [x] Write WebSocket tests using real SQLite alert tables; seeded critical must arrive on a new application connection without an Operator update; invalid bearer is rejected.
- [x] Run `python -m pytest tests/test_safety_state.py -q -p no:cacheprovider` and observe failures.
- [x] Add a database repository read of active alerts and a serialized `refresh` operation on the existing aggregator. Query within the aggregation lock, releasing the database transaction after each read; never retain WebSocket-long transactions.
- [x] Send a fresh state immediately at authenticated connection and application heartbeat from the existing broker, not a concurrent socket writer. On refresh/database error close device streams so they cannot retain GREEN.
- [x] Remove snapshot-based authority from the HTTP safety-state route while preserving active PPE registry updates and response shape.
- [x] Rerun the tests.

## Task 2: Existing alert lifecycle triggers

Files: API `schemas/operator_alerts.py`, `services/operator_alerts.py`, `repositories/safety_alert_repository.py`, `api/routes/operator_alerts.py`, `api/routes/admin_alerts.py`; Operator `api/client.py`, `controllers/application_controller.py`; related API/Operator tests.

- [x] Test create/escalate/resolve through `/operator/alerts`; ensure one occurrence/event, monotonic closure, no unauthorized cross-account mutation, valid resolution timeline and compatible old payloads.
- [x] Test Admin confirmation leaves tower active and closing an alert recalculates immediately.
- [x] Test Operator sends resolved alerts and retains the newest transition while delivery is running.
- [x] Run tests and observe expected failures.
- [x] Extend existing ingestion with optional `status`/`resolved_at`, reusing `alertas.status` and `encerrado_em` (no new table). Maintain legacy hash compatibility and idempotency. Recompute aggregate only after commit.
- [x] Forward local AlertEngine resolution with the existing delivery worker; do not change matching, YOLO or debounce.
- [x] Rerun focused tests and regression tests.

## Task 3: Firmware and setup

Files: existing `firmware/esp32_safety_signal/esp32_safety_signal.ino`, `README.md`, `device_config.example.h`; API `.env.example` if necessary.

- [x] Verify real upstream library names, heartbeat signature and JSON API.
- [x] Add an executable host-side test harness for the state/relay behavior if a C++ compiler is available; otherwise test with Arduino compile tooling and explicitly report any unavailable hardware/toolchain coverage.
- [x] Replace paired ACTIVE HIGH LED code with exactly four active-low relay outputs. Keep optional local config header plus complete inline placeholder defaults for copy/paste.
- [x] Use nonblocking `millis()` blinking, Wi-Fi reconnect, WebSocket heartbeat, strict state/schema validation and application-message watchdog. Invalid JSON never enables GREEN; PONG alone cannot establish/recover authoritative state.
- [x] Compile using installed Arduino tooling if available; never upload to a physical device without a separate request.
- [x] Document dependencies, IP discovery, private-network binding, token generation, placeholders and all six integrated test scenarios. Warn that a relay tower is not a certified safety interlock.

## Verification / handoff

- [x] API tests + Ruff + migration status (no production migration execution).
- [x] Operator targeted tests + full suite where feasible.
- [x] Report pre-existing Admin PPE test failures separately; do not change unrelated Admin code to conceal them.
- [x] Review `git diff --check`, file list and absence of real secrets.
- [x] No commit/push in this request. Return setup/test instructions and the entire final `.ino`.

Verification record: see `../../../firmware/esp32_safety_signal/IMPLEMENTATION.md`. Firmware compiled without a local credentials header; physical bench tests remain manual. No host C++ compiler was present, so firmware coverage is the static contract plus an actual Arduino build, not a simulated circuit.
