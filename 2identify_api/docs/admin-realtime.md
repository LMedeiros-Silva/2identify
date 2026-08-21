# WebSocket administrativo — Etapa 36

Esta etapa estabelece somente o transporte autenticado e o contrato de eventos entre a API e
o Admin. Ela não cria `POST /alerts`, não escreve no PostgreSQL e não publica alertas reais.

## Conexão e autenticação

```http
GET /ws/admin/alerts
Upgrade: websocket
Authorization: Bearer <jwt-admin>
```

O bearer deve estar em exatamente um header `Authorization`. Qualquer query string, mesmo sem
token, e headers ausentes, duplicados ou malformados são rejeitados. O token nunca é registrado
em log.

Antes de aceitar o WebSocket, a API valida algoritmo, assinatura, issuer, audience
`2identify-admin`, claims obrigatórias e expiração. Em seguida reconsulta `usuarios` para confirmar
que a conta permanece ativa e com perfil exatamente `administrador`. A mesma verificação ocorre
a cada heartbeat com uma nova sessão SQLAlchemy curta, fechada ao fim da consulta; nenhuma sessão
de banco permanece aberta pela vida do socket.

Falhas anteriores a `accept()` negam o upgrade por HTTP: `400` para query string, `401` para
autenticação inválida e `503` quando a autorização não pode consultar o banco. Nessa fase ainda
não existe uma conexão WebSocket, portanto o cliente não deve esperar um close code WebSocket.

## Envelope v1

Todo frame enviado pela API é JSON e segue:

```json
{
  "schema_version": 1,
  "event_id": "a5ae1d96-0a91-46e7-aeb4-4af702ea0576",
  "event_type": "connection.ready",
  "occurred_at": "2026-08-20T20:00:00Z",
  "payload": {
    "status": "awaiting_alert_ingestion"
  }
}
```

- `event_id` é um UUID novo para cada envelope;
- `occurred_at` sempre possui timezone e é normalizado para UTC;
- campos extras são proibidos;
- `event_type` aceita apenas os eventos documentados abaixo.

### `connection.ready`

Primeiro evento de uma conexão autorizada:

```json
{"status": "awaiting_alert_ingestion"}
```

Esse estado é intencional: o canal está operacional, mas a ingestão/persistência de alertas ainda
depende de contrato e migration aprovados.

### `connection.heartbeat`

Evento periódico com payload vazio:

```json
{}
```

O intervalo é configurado por `REALTIME_HEARTBEAT_INTERVAL_SECONDS`. A revalidação administrativa
ocorre antes de cada heartbeat. Fora de `testing`, o intervalo mínimo aceito é 5 segundos para
evitar uma tempestade de consultas ao banco.

### `alert.created`

Contrato reservado ao futuro publisher interno, ainda sem produtor nesta etapa:

```json
{
  "alert_id": 17,
  "occurrence_id": 31,
  "level": "critical",
  "status": "nao_lido",
  "summary": "Capacete obrigatório ausente",
  "detected_at": "2026-08-20T20:01:15Z",
  "camera_id": null
}
```

`alert_id` e `occurrence_id` são inteiros positivos; `camera_id` é nulo ou positivo; `level`
aceita `warning` ou `critical`; `status` aceita `nao_lido`, `lido` ou `encerrado`; `summary`
possui de 1 a 500 caracteres. O schema rejeita Base64/data URI, caminhos locais, caracteres de
controle e PII óbvia. `detected_at` é normalizado para UTC. Não existe `sector_id`, pois o schema
atual não vincula alerta ou ocorrência diretamente a setor. Para tolerar somente pequeno desvio
de relógio, `detected_at` não pode ultrapassar `occurred_at` em mais de cinco minutos.

## Backpressure e encerramento

Cada cliente possui uma fila limitada por `REALTIME_CLIENT_QUEUE_CAPACITY`. Quando um cliente não
consegue acompanhar o fluxo, a API não descarta o evento silenciosamente: remove o assinante,
cancela seu writer e encerra a conexão com `1013`.

`REALTIME_MAX_CONNECTIONS` limita o total de sockets e
`REALTIME_MAX_CONNECTIONS_PER_ADMIN` limita sockets simultâneos da mesma conta. Ambos são
aplicados atomicamente pelo broker; overload após o upgrade encerra com `1013`, antes de qualquer
`connection.ready`. `REALTIME_SINK_CLOSE_TIMEOUT_SECONDS` limita separadamente a espera pelo
writer cancelado e pelo fechamento de cada destino, evitando que um cliente travado bloqueie o
shutdown dos demais.

O fluxo é estritamente servidor → cliente. O primeiro frame de texto enviado pelo cliente encerra
com `1008`; um frame binário encerra com `1003`. Execute o Uvicorn com limite de frame explícito:

```powershell
python -m uvicorn app.main:app --reload --ws-max-size 65536
```

Códigos relevantes somente depois que o upgrade foi aceito:

- `4401`: token expirou, conta foi inativada ou perfil foi removido na revalidação periódica;
- `1011`: banco ficou indisponível na revalidação ou a entrega WebSocket falhou;
- `1012`: processo da API em encerramento/reinício;
- `1013`: cliente lento, fila cheia ou capacidade de conexões atingida;
- `1008`: frame de texto do cliente viola a política server-only;
- `1003`: frame binário do cliente não é suportado;
- `1000`: encerramento normal.

## Limites intencionais

- não há produtor nem endpoint público de simulação;
- não há persistência, replay ou garantia de entrega;
- o broker e seus limites são locais ao processo; execute um único worker;
- reiniciar a API encerra os sockets e descarta somente eventos transitórios ainda em fila;
- HTTPS/WSS e rate limiting são obrigatórios antes de exposição fora de `localhost`;
- `POST /alerts`, idempotência e outbox aguardam aprovação do contrato de schema/migration.
