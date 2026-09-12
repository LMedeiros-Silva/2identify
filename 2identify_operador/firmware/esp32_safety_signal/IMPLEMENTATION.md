# Entrega da integração ESP32 — 2026-09-03

Implementação feita na branch `codex/esp32-relay-integration`, sem commit/push.
Base local: `6037d93c557cd223ca485f698e8af73931c7b8a9`.
As alterações anteriores de Gestão de EPI foram preservadas e não fazem parte
desta entrega.

## Arquivos criados nesta integração

- `2identify_api/tests/test_safety_tower_alerts.py`
- `2identify_operador/tests/integration/test_alert_lifecycle_delivery.py`
- `2identify_operador/docs/superpowers/plans/2026-09-02-esp32-relay-integration.md`
- `2identify_operador/firmware/esp32_safety_signal/IMPLEMENTATION.md` (este relatório)

## Arquivos alterados nesta integração

API:
- `2identify_api/README.md`
- `2identify_api/app/core/database.py`
- `2identify_api/app/api/routes/admin_alerts.py`
- `2identify_api/app/api/routes/device_safety.py`
- `2identify_api/app/api/routes/operator_alerts.py`
- `2identify_api/app/api/routes/operator_safety_state.py`
- `2identify_api/app/repositories/safety_alert_repository.py`
- `2identify_api/app/schemas/operator_alerts.py`
- `2identify_api/app/schemas/safety_state.py`
- `2identify_api/app/services/operator_alerts.py`
- `2identify_api/app/services/safety_state.py`
- `2identify_api/tests/test_operations.py`
- `2identify_api/tests/test_safety_state.py`

Operator:
- `2identify_operador/app/api/client.py`
- `2identify_operador/app/controllers/application_controller.py`
- `2identify_operador/app/services/safety_state_service.py`
- `2identify_operador/app/workers/alert_delivery_worker.py`
- `2identify_operador/firmware/esp32_safety_signal/esp32_safety_signal.ino`
- `2identify_operador/firmware/esp32_safety_signal/README.md`
- `2identify_operador/tests/unit/api/test_client.py`
- `2identify_operador/tests/unit/firmware/test_esp32_firmware_contract.py`

Não houve alteração de código do Admin, detecção YOLO/Pose ou AlertEngine.
`SAFETY_DEVICE_TOKEN` já existia em `2identify_api/.env.example`, que foi mantido.
Não foi executada migration no banco real.

## Verificações executadas

- API: `python -m pytest -q -p no:cacheprovider` — **137 passed**.
- Operator: mesmo comando, `QT_QPA_PLATFORM=offscreen` — **292 passed**.
- Admin: `python -m pytest tests/test_alerts_ui.py tests/test_alerts_api_client.py -q -p no:cacheprovider` — **3 testes passaram**.
- Ruff nos arquivos Python tocados: **sem erros**.
- Mypy API `app scripts`: **62 arquivos sem erros**; aviso preexistente de seção
  `psycopg2.*` não utilizada.
- Mypy Operator `app`: **99 arquivos sem erros**.
- `git diff --check`: sem erros.
- `alembic heads`: `e4a7b8c9d0e1`; sem nova revisão nesta integração.
- Arduino CLI **1.5.1**: compilado com alvo `esp32:esp32:esp32`,
  core **3.3.11**, WebSockets **2.7.2**, ArduinoJson **7.4.2**.
  Flash: **1.079.591 bytes / 82%**; variáveis globais: **47.608 bytes / 14%**.
- Compilação usa placeholders, sem `device_config.h` local. Não foi feito upload,
  acionamento de hardware ou alteração de firewall.

A revisão independente encontrou e levou a testes de regressão para:
preservação da maior severidade na resolução, manutenção da notificação ao Admin
quando falha o recálculo da torre e envio de resoluções pendentes no logout,
inclusive quando a thread ainda não iniciou a primeira requisição.

## Limitações verificadas

A coleta completa do Admin falha por três dependências ausentes da etapa anterior:
- `tests/test_ppe_management_api.py`: `app.domain.ppe_management`;
- `tests/test_ppe_management_ui.py`: `app.domain.ppe_management`;
- `tests/test_realtime_protocol.py`: `PpeSessionUpdatedEvent`.

Esses arquivos já estavam alterados antes desta tarefa e foram preservados.
Isso não impediu os testes de alertas do Admin.

O broker é local ao processo: use um worker. Não há outbox durável; após
indisponibilidade prolongada/crash, confira os alertas no Admin. Encerrar uma
operação não comprova resolução do risco e não limpa automaticamente os alertas.
Face ID local com token de catálogo não autoriza publicação de alertas; para o teste
completo use login de operador pela API.

O teste físico está pendente de bancada. O guia `README.md` desta pasta contém
dependências, IP, geração de token, configuração e os seis cenários exigidos.
