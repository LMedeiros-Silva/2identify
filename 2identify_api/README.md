# 2Identify API

Backend independente do 2Identify, iniciado na etapa 33. A API usa FastAPI, SQLAlchemy 2.x
síncrono e PostgreSQL. Também fornece autenticação isolada, dashboard administrativo, ingestão
idempotente de alertas do Operador e canal WebSocket autenticado para o Admin.

## Responsabilidades nesta etapa

- expor `GET /` e `GET /health`;
- manter configuração e credenciais somente no `.env` local;
- abrir conexões PostgreSQL com `pool_pre_ping` e parâmetros ocultos nos erros SQL;
- inspecionar metadados do esquema dentro de uma transação `READ ONLY`;
- preservar a linhagem Alembic já criada pelo Admin;
- fornecer testes que não acessam nem alteram o banco real.
- autenticar contas ativas em `POST /auth/login` com hashes bcrypt compatíveis com o Admin;
- emitir tokens JWT curtos e assinados, sem persistir credenciais ou tokens no banco.
- autenticar exclusivamente administradores em `POST /auth/admin/login`;
- revalidar no banco a conta administrativa em todo recurso protegido;
- expor `GET /admin/me` e `GET /admin/dashboard/summary` somente com bearer de audience Admin.
- expor `WS /ws/admin/alerts` somente a administradores revalidados;
- emitir readiness honesto e heartbeat em envelope versionado;
- isolar clientes lentos com fila limitada e fechamento explícito, sem descarte silencioso.
- receber `POST /operator/alerts` somente de operadores revalidados;
- persistir ocorrência e alerta antes de publicar `alert.created` ao Admin;
- impedir duplicação por UUID e hash do payload em `alertas_ingestao`.

O Admin continua responsável pelas tabelas existentes. A migration compartilhada adiciona apenas
`alertas_ingestao`, usada pela API para idempotência e contexto operacional.

O WebSocket desta etapa é deliberadamente executado em um único processo. Use somente um worker
do Uvicorn até existir um broker distribuído; processos diferentes não compartilham o broker em
memória.

## Instalação no Windows

Na raiz `2identify_api`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite apenas o `.env` e substitua `CHANGE_ME` pela senha do usuário técnico. Não envie esse
arquivo ao Git. O formato esperado é:

```dotenv
DATABASE_URL=postgresql+psycopg2://identify_user:CHANGE_ME@localhost:5432/identify_db
```

Gere também o segredo local de assinatura sem exibi-lo no terminal:

```powershell
python -m scripts.ensure_auth_secret
```

O comando preserva um segredo já válido e só cria/substitui valores ausentes ou placeholders.
Em produção, distribua segredos diferentes por instalação através de um cofre ou mecanismo
seguro de provisionamento.

## Execução

```powershell
python -m uvicorn app.main:app --reload --ws-max-size 65536
```

- API: `http://127.0.0.1:8000`
- saúde: `http://127.0.0.1:8000/health`
- Swagger: `http://127.0.0.1:8000/docs`

O endpoint `/health` retorna HTTP 200 somente após um `SELECT 1` real. Quando o PostgreSQL
está indisponível, retorna HTTP 503 com mensagem sanitizada.

## Login do Operador

O cliente desktop já configurado em `API_URL=http://localhost:8000` envia:

```http
POST /auth/login
Content-Type: application/json
```

```json
{"username": "operador.15", "password": "senha"}
```

A API consulta somente uma conta ativa, verifica o hash bcrypt e retorna um bearer JWT com
30 minutos de validade por padrão. A resposta inclui `operator.id=usuarios.id`, nome, perfil e
foto `null`, pois ainda não existe vínculo confiável entre `usuarios` e `funcionarios`.

Usuário inexistente, senha incorreta, senha acima do limite seguro do bcrypt, conta inativa e
perfil não permitido recebem a mesma resposta HTTP 401. Falhas do PostgreSQL recebem HTTP 503
sem detalhes internos. Todas as respostas de autenticação usam `Cache-Control: no-store`, e os
erros de validação nunca refletem os valores recebidos.

Por padrão e por contrato, `/auth/login` aceita somente `operador`. Não adicione
`administrador` a `AUTH_ALLOWED_PROFILES`: o Admin possui o endpoint e o audience JWT
separados descritos abaixo.

Fora de `localhost`, publique a API exclusivamente atrás de HTTPS e com limitação de tentativas
no proxy ou em uma infraestrutura compartilhada, como Redis. A API não implementa bloqueio
persistente nesta etapa porque isso exige política e infraestrutura próprias.

## Integração do Admin

O Admin autentica uma conta ativa com perfil `administrador` em `POST /auth/admin/login`.
A resposta contém `administrator` com `id`, `name`, `username` e `profile`, além de um JWT com
audience `2identify-admin`. Esse token não funciona nos recursos do Operador, e tokens do
Operador não funcionam nos recursos do Admin.

Envie o token em `Authorization: Bearer <token>` para:

- `GET /admin/me`, que reconsulta a conta ativa e o perfil pelo `sub` do token;
- `GET /admin/dashboard/summary`, que retorna contagens de funcionários ativos, atribuições e
  entregas de EPI, percentual de entrega, alertas totais/críticos e agregações para gráficos:
  evolução dos últimos sete dias, categorias e situação do tratamento administrativo.

`ppe_delivery_percentage` é apenas uma razão de entregas; não representa conformidade ou
garantia de segurança industrial. Todas as respostas desses endpoints usam
`Cache-Control: no-store`. Consulte `docs/admin-integration.md` para o contrato completo.

O canal administrativo em tempo real fica em `WS /ws/admin/alerts`. O JWT deve ser enviado
exclusivamente no header `Authorization: Bearer`; qualquer query string é rejeitada porque URLs
podem aparecer em histórico, telemetria e access logs. Falhas antes do upgrade são respostas HTTP,
não close codes WebSocket. A API revalida periodicamente assinatura, expiração, audience, conta
ativa e perfil administrativo usando uma sessão curta de banco por ciclo. Limites globais e por
administrador impedem criação ilimitada de filas, tarefas e consultas periódicas. Consulte
`docs/admin-realtime.md` para o envelope, códigos posteriores ao upgrade e as limitações
intencionais desta etapa.

## Alertas do Operador

`POST /operator/alerts` exige o mesmo bearer `2identify-operator` emitido no login. O corpo contém
UUID do evento e da sessão de trabalho, operação, câmera/área opcionais, tipo, chave de
deduplicação, resumo, severidade e timestamps UTC. O primeiro envio retorna `201`; uma repetição
idêntica retorna `200` com `duplicate=true`; reutilizar o UUID com outro payload retorna `409`.
O Admin recebe a categoria `ergonomics`, `ppe`, `risk_area` ou `monitoring` no evento WebSocket.

## Tratamento de alertas pelo Admin

Os endpoints abaixo exigem bearer administrativo e retornam `Cache-Control: no-store`:

- `GET /admin/alerts`: histórico com alerta, ocorrência, funcionário, câmera, setores,
  evidências e contexto operacional;
- `GET /admin/alerts/{id}`: detalhe de um alerta;
- `PATCH /admin/alerts/{id}/confirm`: confirma o recebimento e audita administrador/data;
- `PATCH /admin/alerts/{id}/close`: encerra a ocorrência após a confirmação.

O encerramento antes da confirmação retorna `409`. Repetir uma confirmação ou um encerramento
já concluído é idempotente, desde que o alerta permaneça em um estado compatível.

## Operações e áreas de risco

Os recursos administrativos abaixo exigem o bearer do Admin:

- `GET /admin/operations/catalog`: câmeras, EPIs e setores ativos;
- `POST /admin/cameras`: cadastra uma câmera associada a um setor ativo;
- `GET|POST /admin/risk-areas` e `PUT /admin/risk-areas/{id}`;
- `GET|POST /admin/operations` e `PUT /admin/operations/{id}`.

`areas_risco.geometria` é JSONB no formato `polygon`, com ao menos três pontos
normalizados entre `0.0` e `1.0`. A API rejeita vértices repetidos, área zero e
auto-interseção. Operações exigem uma área ativa e ao menos um EPI ativo.

O Operador possui somente leitura em `GET /operator/operations`; a resposta usa
o mesmo polígono persistido para permitir a projeção sobre qualquer resolução de
câmera. A troca do provider mock do desktop Operador por esse endpoint permanece
como uma etapa separada.

Antes de qualquer exposição fora do computador local, remova credenciais previsíveis de seed,
gere um segredo JWT exclusivo, habilite HTTPS e limitação de tentativas no proxy. O comando de
desenvolvimento acima mantém o bind padrão do Uvicorn em `127.0.0.1`; não use `--host 0.0.0.0`
até concluir esse endurecimento.

## Inspeção segura do esquema

```powershell
python -m scripts.inspect_schema
```

O comando lista somente metadados (tabelas, colunas, chaves, índices e versão Alembic). Ele
não lê registros de negócio e executa em transação somente leitura.

## Qualidade

```powershell
python -m pytest
python -m ruff check .
python -m mypy app scripts
```

Os testes injetam um banco falso; portanto podem ser executados sem PostgreSQL e sem risco de
alterar os dados reais.

## Alembic

A pasta `alembic/versions` contém cópias idênticas das revisões do Admin. Depois de backup,
aplique uma única vez `python -m alembic upgrade head` a partir da API ou do Admin.
O autogenerate continua bloqueado. Consulte `alembic/README.md`.

## Próxima etapa

A fila offline/outbox durável do Operator permanece fora desta entrega. O endpoint
de operações já está disponível; o desktop Operador ainda usa o provider mock até
a etapa de integração. Face ID continua local somente em desenvolvimento/testes.
