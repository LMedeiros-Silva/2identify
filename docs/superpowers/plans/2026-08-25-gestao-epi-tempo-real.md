# Plano de implementação — Gestão de EPI em tempo real

> **Objetivo:** entregar a tela administrativa em tempo real reutilizando o snapshot de segurança, o broker e o WebSocket existentes.

## 1. Ampliar o snapshot do Operador

**Arquivos:**
- Alterar `2identify_operador/app/services/safety_state_service.py`
- Alterar `2identify_operador/app/controllers/active_ppe_monitoring_controller.py`
- Alterar `2identify_operador/app/controllers/application_controller.py`
- Alterar `2identify_operador/app/api/client.py`
- Testar serviços, controlador e cliente nos arquivos de teste correspondentes.

Escrever primeiro testes para estados de PPE, snapshot inicial, atualização imediata, heartbeat e encerramento. Depois ampliar o modelo e serialização, mantendo a resposta de hardware compatível.

## 2. Registrar e publicar sessões ativas na API

**Arquivos:**
- Alterar `2identify_api/app/schemas/safety_state.py`
- Criar `2identify_api/app/schemas/active_operations.py`
- Criar `2identify_api/app/services/active_operations.py`
- Alterar `2identify_api/app/services/operations.py`
- Alterar `2identify_api/app/api/routes/operator_safety_state.py`
- Criar `2identify_api/app/api/routes/admin_active_operations.py`
- Alterar composição, exports e `2identify_api/app/schemas/realtime.py`
- Testar operações ativas e os contratos de safety-state/realtime.

Escrever testes para autenticação, enriquecimento pelo catálogo, rejeição de divergências, snapshot inicial, evento `ppe.session.updated`, atualização idempotente e remoção por `ended`.

## 3. Consumir snapshot e realtime no Admin

**Arquivos:**
- Criar `2identify_admin/app/domain/ppe_management.py`
- Alterar `2identify_admin/app/api/client.py`
- Criar serviço, controlador e worker de Gestão de EPI
- Alterar domínio/protocolo/controlador realtime
- Testar contratos, cliente, worker e controladores antes da implementação.

O carregamento inicial será HTTP em worker; eventos posteriores atualizarão o estado sem polling. Reconexão pedirá novo snapshot para recuperar eventos perdidos.

## 4. Criar a tela Gestão de EPIs

**Arquivos:**
- Criar `2identify_admin/app/ui/ppe/ppe_management_page.py` e `__init__.py`
- Alterar `2identify_admin/app/ui/main/main_window.py`
- Alterar `2identify_admin/app/controllers/application_controller.py`
- Adicionar estilos mínimos no tema atual
- Criar testes UI e de integração do shell.

Construir resumo, busca, filtro, cards, estados de PPE, duração local, placeholder de foto, estado vazio e conexão offline mantendo o último snapshot.

## 5. Verificação integrada

Executar testes focados a cada ciclo vermelho/verde e, ao final, as suítes completas dos módulos API, Admin e Operador, além de lint/type-check configurados no repositório. Revisar `git diff` para preservar alterações preexistentes do ajuste de `protetor_headset`.
