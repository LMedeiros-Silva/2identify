# PoC Mobile de Alertas com Supabase — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar uma PoC web mobile para administradores autenticados consultarem alertas pela FastAPI existente, executada contra uma cópia manual, segura e idempotente do PostgreSQL local no Supabase.

**Architecture:** O sistema principal continua `Admin/Operator -> FastAPI local -> PostgreSQL local`. Processos exclusivos da PoC carregam `2identify_api/.env.mobile`, validam rigorosamente os dois bancos e promovem `CLOUD_DATABASE_URL` a `DATABASE_URL` apenas no processo filho. As migrations Alembic existentes criam o schema cloud por um bootstrap controlado; um sincronizador transacional copia somente as nove tabelas necessárias. O frontend estático `2identify_web` chama apenas a FastAPI e reutiliza o JWT administrativo existente.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/psycopg2, pytest, HTML/CSS, JavaScript ES modules, Node.js `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-09-mobile-alerts-supabase-poc-design.md`

## Global Constraints

- Não alterar `2identify_api/.env`, migrations históricas, Operator, Admin desktop, ESP32, PPE, Pose Estimation, Face ID, área de risco ou AlertEngine.
- Não executar `DROP`, `TRUNCATE`, downgrade, reset ou exclusão automática.
- Nunca imprimir URL completa, senha, hash de senha ou JWT.
- Não fazer commit, push, merge ou PR nesta entrega.
- Antes de qualquer DDL cloud, exigir preflight aprovado e schema vazio ou estado intermediário exatamente reconhecido.
- Parar imediatamente diante de destino ambíguo, schema inesperado, diferença estrutural antes do stamp ou migration posterior destrutiva.

---

## Task 1: Isolar configuração mobile e validar destinos

**Files:**
- Modify: `../2identify_api/.gitignore`
- Create: `../2identify_api/.env.mobile.example`
- Create: `../2identify_api/app/mobile_poc/__init__.py`
- Create: `../2identify_api/app/mobile_poc/config.py`
- Create: `../2identify_api/tests/test_mobile_poc_config.py`

- [x] Escrever testes que exijam: carregamento separado de `DATABASE_URL` e `CLOUD_DATABASE_URL`; PostgreSQL/psycopg2; host cloud terminado em `.supabase.co`; origem e destino diferentes; destino mascarado; ausência de segredo na representação e nos erros.
- [x] Executar `py -m pytest tests/test_mobile_poc_config.py -q` e confirmar falha inicial.
- [x] Implementar parser imutável com `sqlalchemy.engine.make_url`, normalização de driver somente em memória e comparação por host/porta/banco.
- [x] Adicionar `.env.mobile` ao `.gitignore` e criar `.env.mobile.example` apenas com placeholders seguros e `MOBILE_CORS_ORIGINS` explícito.
- [x] Implementar carregamento que combina `.env` somente para origem/segredos da API e `.env.mobile` somente para configuração da PoC, sem alterar arquivos ou ambiente pai.
- [x] Reexecutar o teste focado e confirmar aprovação.

## Task 2: Inventariar schema e auditar migrations sem executar DDL

**Files:**
- Create: `../2identify_api/app/mobile_poc/schema.py`
- Create: `../2identify_api/app/mobile_poc/migrations.py`
- Create: `../2identify_api/tests/test_mobile_poc_schema.py`
- Create: `../2identify_api/tests/test_mobile_poc_migrations.py`

- [x] Escrever testes de snapshot estrutural cobrindo tabelas, colunas, tipos, nulabilidade, defaults, PKs, FKs, índices, uniques e sequences/identity.
- [x] Escrever testes que aceitem apenas schema cloud vazio ou revisão/estrutura intermediária conhecida e rejeitem tabela, revisão, coluna ou constraint inesperada.
- [x] Escrever auditoria estática que bloqueie `drop_table`, `drop_column`, `drop_constraint`, `TRUNCATE`, SQL destrutivo e alterações com perda potencial; validar a cadeia real de revisions/down_revisions.
- [x] Executar os testes focados e confirmar falha inicial.
- [x] Implementar introspecção canônica via SQLAlchemy Inspector e consultas PostgreSQL somente de metadados.
- [x] Implementar comparação do estado após `42d54200970a` com o estado físico esperado por `441c04c14c57`; o resultado precisa ser integralmente equivalente antes de permitir stamp.
- [x] Registrar explicitamente as revisões: normais antes do stamp (`5e2716b5ed84`, `42d54200970a`), puladas (`d5338781e8f0`, `441c04c14c57`) e normais posteriores (`7b9d2e4f6a81`, `c8f1e2a3b4d5`, `e4a7b8c9d0e1`).
- [x] Reexecutar os testes e confirmar aprovação.

## Task 3: Criar bootstrap Alembic seguro e retomável

**Files:**
- Create: `../2identify_api/app/mobile_poc/bootstrap.py`
- Create: `../2identify_api/scripts/prepare_mobile_poc_supabase.py`
- Create: `../2identify_api/tests/test_prepare_mobile_poc_supabase.py`

- [x] Escrever testes com executor falso para provar que nenhum comando mutante roda antes do preflight, que incompatibilidade impede stamp e que uma revisão desconhecida encerra o fluxo.
- [x] Testar a ordem exata: `upgrade 42d54200970a` -> comparação física -> `stamp 441c04c14c57` -> nova validação -> auditoria das migrations posteriores -> `upgrade head` -> validação final.
- [x] Implementar flags `--preflight-only` e `--apply`, com `--apply` explícito para DDL; nenhum modo oferece downgrade ou limpeza.
- [x] Executar Alembic com URL cloud passada somente ao ambiente do subprocesso e nunca nos argumentos/logs.
- [x] Validar ao final `alembic current`, `alembic heads`, revision `e4a7b8c9d0e1` e compatibilidade estrutural cloud x local.
- [x] Reexecutar testes focados.

## Task 4: Implementar sincronização seletiva, transacional e idempotente

**Files:**
- Create: `../2identify_api/app/mobile_poc/sync.py`
- Create: `../2identify_api/scripts/sync_mobile_poc_to_supabase.py`
- Create: `../2identify_api/tests/test_mobile_poc_sync.py`

- [x] Escrever testes para a ordem fixa: `usuarios`, `setores`, `cameras`, `funcionarios`, `ocorrencias`, `areas_risco`, `operacoes`, `alertas`, `alertas_ingestao`.
- [x] Testar validação dessa lista contra models, PKs e FKs reais; confirmar que autenticação Admin usa somente `usuarios` (`perfil`, `ativo`, `senha_hash`) e que tabelas EPI não são copiadas.
- [x] Testar `--dry-run`: somente destino mascarado, ordem e contagens; zero escrita e nenhuma linha/hash impresso.
- [x] Testar leitura local em transação `READ ONLY`, uma única transação cloud, rollback total em erro, IDs preservados e upsert por PK sem DELETE.
- [x] Testar duas execuções sem duplicação e um update por fixture controlada.
- [x] Implementar `INSERT ... ON CONFLICT DO UPDATE` com reflexão e lista permitida fixa.
- [x] Após upsert, ajustar somente sequences/identity das tabelas relevantes para valor seguro maior ou igual ao maior ID, sem reduzir sequence existente.
- [x] Validar contagens, PKs duplicadas, FKs e sequences após commit.
- [x] Reexecutar testes focados.

## Task 5: Acrescentar nome da operação ao contrato existente de alertas

**Files:**
- Modify: `../2identify_api/app/repositories/admin_alert_repository.py`
- Modify: `../2identify_api/app/services/admin_alerts.py`
- Modify: `../2identify_api/app/schemas/admin_alerts.py`
- Modify: `../2identify_api/tests/test_admin_alerts.py`

- [x] Criar testes do endpoint existente para `operation_id` válido retornar `operation_name` e para ID inexistente/nulo manter o alerta com operação nula, sem erro.
- [x] Confirmar falha dos novos testes.
- [x] Acrescentar `LEFT OUTER JOIN` entre `alertas_ingestao.operacao_id` e `operacoes.id`.
- [x] Expor o nome como campo opcional, de forma aditiva e compatível com os clientes Admin atuais.
- [x] Reexecutar `tests/test_admin_alerts.py` e testes de autenticação administrativa.

## Task 6: Configurar CORS e comando isolado da API cloud

**Files:**
- Modify: `../2identify_api/app/core/config.py`
- Modify: `../2identify_api/app/main.py`
- Create: `../2identify_api/scripts/run_mobile_poc_api.py`
- Modify: `../2identify_api/tests/test_config.py`
- Create: `../2identify_api/tests/test_mobile_poc_api.py`

- [x] Escrever testes garantindo CORS vazio por padrão e allowlist explícita, sem `*`, apenas métodos/headers necessários.
- [x] Escrever teste do launcher garantindo que `DATABASE_URL` só muda no processo filho, preservando `.env` e shell pai.
- [x] Implementar `MOBILE_CORS_ORIGINS` validado e instalar `CORSMiddleware` somente quando houver origens configuradas.
- [x] Implementar launcher cloud mascarado, sem logar URL/JWT e reutilizando a mesma aplicação FastAPI.
- [x] Reexecutar testes focados, incluindo health, login e `/admin/alerts`.

## Task 7: Criar frontend mobile estático

**Files:**
- Create: `../2identify_web/index.html`
- Create: `../2identify_web/styles.css`
- Create: `../2identify_web/alerts.js`
- Create: `../2identify_web/controller.js`
- Create: `../2identify_web/app.js`
- Create: `../2identify_web/package.json`
- Create: `../2identify_web/tests/alerts.test.mjs`

- [x] Escrever testes JavaScript primeiro para classificação/filtros, renderização segura, formatação, API indisponível, 401, atualização manual, polling e logout.
- [x] Executar `npm test` em `2identify_web` e confirmar falha inicial. (`node --test`, pois `npm` não está instalado neste host.)
- [x] Implementar login via `POST /auth/admin/login`, alertas via `GET /admin/alerts`, Authorization Bearer e token apenas em `sessionStorage`.
- [x] Implementar filtros Todos/Críticos/Atenção/Resolvidos, cards, estados loading/vazio/erro/sessão expirada, refresh manual, polling leve e cancelamento no logout.
- [x] Mostrar somente indicador de evidência quando existir caminho local; nunca gerar link para arquivo local.
- [x] Implementar layout mobile-first para 390x844, `box-sizing: border-box`, containers flexíveis e nenhuma largura que cause overflow horizontal.
- [x] Reexecutar `npm test`. (`node --test`: 8 testes aprovados.)

## Task 8: Executar preflight, bootstrap e sincronização no Supabase

**Files:**
- Local secret only: `../2identify_api/.env.mobile` (ignorado; nunca mostrar conteúdo)
- Create: `../2identify_api/scripts/configure_mobile_poc.py`
- Create: `../2identify_api/tests/test_configure_mobile_poc.py`

- [x] Confirmar com `git check-ignore` que `.env.mobile` está ignorado e que `.env` permanece intacto.
- [x] Carregar a credencial cloud por entrada segura/ambiente sem eco; não incluí-la em comando, documentação ou saída.
- [x] Rodar preflight somente leitura e registrar exclusivamente o destino mascarado e estado reconhecido.
- [x] Auditar todas as migrations reais posteriores ao stamp e parar se houver operação destrutiva inesperada.
- [x] Rodar bootstrap com `--apply` somente após as validações anteriores.
- [x] Rodar `alembic current`, `alembic heads` e comparação física completa cloud x local.
- [x] Rodar sincronização `--dry-run`, verificar as nove contagens previstas e ausência de escrita.
- [x] Rodar sincronização real uma vez e validar contagens/FKs/sequences.
- [x] Rodar sincronização real uma segunda vez e comprovar contagens idênticas e ausência de duplicação.
- [x] Manter o teste de atualização restrito a fixture/transação de teste; não modificar dados reais do usuário.

## Task 9: Validar integração e regressões sem commit

**Files:**
- Inspect only: `../2identify_api`, `../2identify_web`, `.`

- [x] Iniciar a API cloud pelo launcher isolado e validar `/health` sem expor configuração.
- [ ] Validar login administrativo real com credencial fornecida por entrada segura; não registrar senha nem JWT.
- [ ] Validar `/admin/alerts`, nome de operação, operação lógica ausente e filtros.
- [ ] Iniciar `2identify_web` com servidor HTTP local e validar login, lista, filtros, refresh, polling, logout, erro de API e sessão.
- [x] Validar visualmente viewport 390x844 e medir `document.documentElement.scrollWidth <= innerWidth`.
- [x] Executar toda a suíte da API, testes do frontend, lint e type-check da PoC; registrar separadamente avisos de lint preexistentes fora do escopo.
- [ ] Executar testes relevantes do Operator e Admin sem modificar seus códigos. (Operator: 292 aprovados. Admin: coleta bloqueada por módulos preexistentes ausentes em Gestão de EPI.)
- [x] Inspecionar `git status` e `git diff --check`; confirmar que nenhum segredo, `.env.mobile`, biometria, log ou artefato temporário será versionado.
- [ ] Produzir relatório final com plano, arquivos, estado/revision do Supabase, migrations normais/puladas/pós-stamp, contagens por tabela, idempotência, endpoints, frontend, comandos de execução, endereço LAN, testes e limitações — sem segredos.
