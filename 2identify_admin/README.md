# 2Identify Admin

Cliente desktop PySide6 para administração do 2Identify. A partir da Etapa 35,
o login e o dashboard usam exclusivamente a API HTTP. Esses dois fluxos não
abrem conexão PostgreSQL e não possuem fallback local.

## Preparação

1. Crie e ative uma virtualenv com Python 3.11 ou superior.
2. Instale as dependências com `python -m pip install -r requirements.txt`.
3. Copie `.env.example` para `.env` e ajuste `API_URL` para o endereço da API.
4. Inicie a API antes do desktop.
5. Execute `python main.py`.

Rotas consumidas:

- `POST /auth/admin/login`
- `GET /admin/me`
- `GET /admin/dashboard/summary`

O token JWT permanece somente em memória, não é escrito em arquivo ou log e é
descartado no logout, na expiração da sessão e no encerramento da aplicação.
Erros de conexão mantêm o login recuperável e exibem “Tentar novamente” no
dashboard sem bloquear a thread da interface.

## Configuração

As opções do desktop são tipadas em `app/core/config.py`:

- `API_URL`
- `API_CONNECT_TIMEOUT_SECONDS` (HTTP e handshake do WebSocket)
- `API_READ_TIMEOUT_SECONDS`
- `API_WRITE_TIMEOUT_SECONDS`
- `API_POOL_TIMEOUT_SECONDS`
- `LOG_LEVEL`
- `LOG_DIRECTORY` (opcional)

`DATABASE_URL` continua disponível somente para Alembic, seed e outras
ferramentas legadas. Alterações de schema continuam sendo feitas pelos comandos
de migração existentes; o desktop não executa migration automaticamente.

## Seed legado

`seed.py` não possui senha fixa. Ao criar um administrador no futuro, informe
`ADMIN_SEED_PASSWORD` pelo ambiente ou digite o segredo via prompt oculto. A
senha deve ter ao menos 12 caracteres e nunca é impressa.

Essa alteração protege apenas provisionamentos futuros: ela **não rotaciona a
senha de contas que já existem no PostgreSQL**. Instalações antigas devem trocar
a senha administrativa antes de expor a API para outra máquina ou rede.

O seed modifica o banco. Não o execute apenas para testar a interface.

Remover a senha fixa do código não rotaciona contas já existentes. Instalações
criadas com o seed histórico devem trocar a credencial administrativa por um
fluxo autorizado antes de expor a API fora de `localhost`.

## Tempo real — Etapa 36

Depois do login, o Admin abre `WS(S) /ws/admin/alerts` usando
`PySide6.QtWebSockets.QWebSocket`. A URL é derivada de `API_URL`: `http` vira
`ws` apenas em loopback, enquanto `https` vira `wss`. O JWT é enviado somente
no cabeçalho `Authorization: Bearer`; ele não aparece na URL, em logs ou no
`repr` dos objetos de sessão.

O cliente aceita exclusivamente envelopes v1 limitados a 64 KiB para
`connection.ready`, `connection.heartbeat` e `alert.created`. Eventos de alerta
alimentam uma lista efêmera e um banner e solicitam, com debounce, uma nova
leitura HTTP do dashboard. Os cards nunca são incrementados localmente.

O estado “Conectado — aguardando integração de alertas” é intencional: nesta
etapa ainda não existe produtor real de `alert.created`. O broker é em memória;
não há replay, durabilidade, garantia entre múltiplos workers nem recuperação
de mensagens após reinício. Essas garantias pertencem à etapa de outbox
durável e não são simuladas pelo desktop.

Falhas de rede mantêm a sessão e usam reconexão com backoff e jitter. Uma
tentativa que permanece presa no handshake é abortada após
`API_CONNECT_TIMEOUT_SECONDS` e entra no mesmo backoff. Uma
rejeição de autorização no WebSocket é revalidada por `GET /admin/me`; somente
uma rejeição real do bearer retorna ao login. Erros TLS nunca são ignorados.

Enquanto a API estiver sem HTTPS e sem limitação compartilhada de tentativas de
login, mantenha `API_URL` apontando para o loopback (`127.0.0.1`/`localhost`).
Qualquer implantação em rede exige HTTPS e rate limiting no proxy ou gateway.

## Testes

Os testes HTTP usam `httpx.MockTransport`; não acessam rede nem banco:

```powershell
python -m pytest
```

Para testes de UI em ambiente sem tela, defina `QT_QPA_PLATFORM=offscreen`.
