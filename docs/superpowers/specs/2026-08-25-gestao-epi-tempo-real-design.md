# Gestão de EPI em tempo real — desenho aprovado

## Escopo

Implementar no Admin uma visão em tempo real das operações ativas e dos estados de EPI já calculados pelo Operador. A primeira versão publica somente sessões autenticadas por e-mail/senha, pois o Face ID atual é local e não possui bearer da API.

## Arquitetura

O Operador continuará usando `PpeStabilityEngine` e `PpeSafetyEngine` como única fonte dos estados `collecting`, `confirmed`, `absent`, `unstable` e `unmapped`. O snapshot já enviado a `PUT /operator/safety-state` será ampliado com início da sessão, situação ativa/encerrada e os estados dos EPIs. O endpoint continuará protegido pelo bearer do operador e continuará respondendo com o estado compacto usado pelo hardware.

A API validará a operação e os EPIs pelo catálogo persistido, obterá nome e identificador do operador pelo principal autenticado e manterá um registro process-local dos snapshots ativos. O registro não será histórico e não exige migration. `GET /admin/active-operations` fornecerá o snapshot inicial autenticado. Alterações serão publicadas pelo broker existente no mesmo WebSocket administrativo, com o evento `ppe.session.updated`.

O Admin carregará o snapshot inicial ao abrir a sessão e aplicará eventos posteriores sem polling. A página Gestão de EPIs manterá o último snapshot conhecido durante indisponibilidade, mostrará o estado discreto da conexão e atualizará duração e frescor localmente por timer, sem consultar a API novamente.

## Contrato mínimo

O Operador envia somente identificadores, timestamps e estados produzidos pelo pipeline. Nomes de operador, operação, câmera e EPIs são enriquecidos pela API. Um snapshot encerrado remove a sessão ativa. Um snapshot ativo precisa corresponder exatamente aos EPIs obrigatórios da operação.

O evento `ppe.session.updated` usa o envelope realtime v1 existente e inclui um snapshot administrativo com status `active` ou `ended`. A foto não será transmitida nesta versão: a API atual não possui referência segura de foto; o Admin usará placeholder.

## Conformidade

- `conforme`: todos os EPIs em `confirmed`.
- `atencao`: ao menos um EPI em `collecting` ou `unstable`, sem estado bloqueante.
- `nao_conforme`: ao menos um EPI em `absent` ou `unmapped`.

## Interface

A página seguirá a navegação e o estilo PySide6 atuais. Terá resumo de operadores online, conformes e com alerta; busca simples; filtro de conformidade; cards com operador, identificador, operação, início, duração, câmera, EPIs obrigatórios e estado geral; estado vazio; e indicador de conexão preservando dados já recebidos.

## Segurança e resiliência

- Admin não acessa PostgreSQL diretamente.
- Operador não envia nome confiável nem escolhe outro operador no payload.
- Token do catálogo não será aceito para publicação.
- Face ID local não publicará até existir autenticação reconhecida pela API.
- O fluxo reutiliza o endpoint de segurança, o broker e o WebSocket existentes.
- O encerramento limpo envia snapshot `ended`; snapshots periódicos restauram o registro após reinício da API.

## Verificação

Testes cobrirão contratos de domínio/transporte, validação da API, registro e eventos realtime, cliente e controlador Admin, UI, mudança de estados e remoção ao encerrar. As suítes dos três módulos serão executadas ao final.
