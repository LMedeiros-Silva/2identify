# PoC mobile de alertas com Supabase — design

## Objetivo

Criar uma PoC web responsiva para administradores consultarem alertas do
2Identify pelo celular. A PoC executará a FastAPI existente contra uma cópia
manual dos dados no Supabase, mantendo o fluxo principal Admin + Operator →
FastAPI local → PostgreSQL local integralmente preservado.

O PostgreSQL local continuará sendo selecionado exclusivamente por
`DATABASE_URL`. A PoC usará `CLOUD_DATABASE_URL` somente em processos iniciados
por comandos próprios da PoC. Nenhum segredo será versionado, exibido em logs,
incluído em documentação ou retornado por endpoints.

## Decisões arquiteturais

1. A estrutura cloud será criada com as migrations Alembic existentes, mas a
   sequência intermediária destrutiva será pulada de forma controlada.
2. A cópia de dados será manual, transacional e idempotente, usando upsert sem
   exclusões.
3. A API cloud será a mesma FastAPI, iniciada em processo isolado com a URL cloud.
4. O frontend será uma aplicação web estática e responsiva em `2identify_web`,
   sem reconstruir o Admin.
5. A autenticação continuará sendo `/auth/admin/login`; a listagem continuará
   sendo `/admin/alerts` com o mesmo JWT administrativo.
6. O frontend usará polling leve e atualização manual. O WebSocket não faz parte
   desta PoC.

## Estado atual validado

O banco local possui as tabelas `usuarios`, `setores`, `cameras`,
`funcionarios`, `epis`, `funcionario_epis`, `ocorrencias`, `alertas`,
`alertas_ingestao`, `areas_risco`, `operacoes` e `operacao_epis`, além de
`alembic_version`.

O endpoint `/admin/alerts` forma os detalhes por meio dos relacionamentos:

- `alertas.ocorrencia_id → ocorrencias.id`;
- `ocorrencias.funcionario_id → funcionarios.id`;
- `funcionarios.setor_id → setores.id`;
- `ocorrencias.camera_id → cameras.id`;
- `cameras.setor_id → setores.id`;
- `alertas_ingestao.alerta_id → alertas.id`;
- `alertas_ingestao.operador_usuario_id → usuarios.id`;
- `alertas.confirmado_por → usuarios.id`;
- `alertas.encerrado_por → usuarios.id`.

`alertas_ingestao.operacao_id` é uma referência lógica, sem Foreign Key física,
para `operacoes.id`. O nome da operação é necessário na interface mobile; o
endpoint existente receberá uma extensão aditiva e compatível para expor esse
nome por `LEFT JOIN`, sem criar outra lógica de alertas.

`operacoes.area_risco_id → areas_risco.id` e
`areas_risco.camera_id → cameras.id` completam as dependências físicas da
operação. Consequentemente, somente estas tabelas terão dados sincronizados, na
ordem abaixo:

1. `usuarios`;
2. `setores`;
3. `cameras`;
4. `funcionarios`;
5. `ocorrencias`;
6. `areas_risco`;
7. `operacoes`;
8. `alertas`;
9. `alertas_ingestao`.

`epis`, `funcionario_epis` e `operacao_epis` existirão no schema criado pelas
migrations, mas não terão dados copiados porque não participam da consulta de
alertas nem da autenticação administrativa da PoC.

## Configuração e segredos

`2identify_api/.env` permanecerá inalterado. A configuração cloud ficará em
`2identify_api/.env.mobile`, ignorado pelo Git, contendo apenas valores locais de
execução, incluindo `CLOUD_DATABASE_URL` e as origens CORS explícitas.

`2identify_api/.env.mobile.example` será versionável e conterá somente
placeholders. O preflight converterá a URL PostgreSQL para o driver
`postgresql+psycopg2` somente em memória e preservará caracteres especiais por
codificação apropriada.

Logs poderão exibir apenas um destino mascarado, como
`db.ly***.supabase.co:5432/postgres`. Senha, URL integral, hashes de senha e JWTs
nunca serão registrados. Erros de banco serão apresentados por categoria e tipo,
sem incluir mensagens de exceção que possam carregar a URL.

## Preflight cloud

Antes de qualquer DDL ou sincronização, o processo deverá:

1. carregar `DATABASE_URL` local e `CLOUD_DATABASE_URL` separadamente;
2. validar ambas com o parser de URLs do SQLAlchemy;
3. exigir PostgreSQL com driver psycopg2;
4. exigir host cloud terminado em `.supabase.co`;
5. rejeitar igualdade de host, porta e banco entre origem e destino;
6. conectar aos dois bancos sem imprimir URLs;
7. inspecionar somente o schema configurado, inicialmente `public`;
8. aceitar o cloud apenas se estiver vazio ou em um estado Alembic reconhecido
   produzido por este fluxo;
9. interromper em tabelas, revisões, colunas ou constraints inesperadas;
10. verificar estaticamente que cada upgrade que será executado não contém
    `drop_table`, `drop_column`, `drop_constraint`, `truncate` ou SQL destrutivo.

O preflight não executará DDL. Uma opção `--dry-run` encerrará após diagnóstico,
plano de tabelas e contagens, sem gravar dados.

## Bootstrap Alembic sem DROP

A cadeia histórica contém as revisões `d5338781e8f0` e `441c04c14c57`. A primeira
remove `usuarios.atualizado_em` e altera `usuarios.criado_em`; a segunda restaura
o estado anterior. Elas se anulam no schema final, mas a primeira executaria um
`DROP COLUMN`, proibido nesta PoC.

Em um schema cloud vazio, o bootstrap seguirá exatamente:

1. executar normalmente `5e2716b5ed84` e `42d54200970a` por meio de
   `alembic upgrade 42d54200970a`;
2. validar que `usuarios.criado_em` e `usuarios.atualizado_em` já possuem a forma
   final esperada e que todas as tabelas criadas estão vazias;
3. executar `alembic stamp 441c04c14c57`, registrando explicitamente que
   `d5338781e8f0` e `441c04c14c57` foram puladas;
4. verificar novamente revisão e estrutura;
5. executar normalmente `7b9d2e4f6a81`, `c8f1e2a3b4d5` e `e4a7b8c9d0e1`
   por meio de `alembic upgrade head`;
6. conferir `alembic current`, `alembic heads` e presença de
   `e4a7b8c9d0e1` como revisão final;
7. comparar tabelas, colunas, tipos, nulabilidade, chaves primárias, uniques,
   índices e Foreign Keys entre cloud e local.

Se o schema não estiver vazio antes do primeiro bootstrap, somente será aceito um
estado intermediário exato e reconhecido desse procedimento. Qualquer outro
estado causará parada antes de escrita. Nenhum comando de downgrade, DROP,
TRUNCATE, reset ou exclusão será oferecido automaticamente.

## Sincronização seletiva

`scripts/sync_mobile_poc_to_supabase.py` fará a sincronização explícita. Ele usará
reflection para validar as nove tabelas permitidas contra os schemas reais e uma
lista fixa para impedir que tabelas adicionais sejam copiadas acidentalmente.

Para cada tabela, o script lerá os registros locais e executará upsert no cloud
pela chave primária. IDs, UUIDs, timestamps, valores nulos e hashes bcrypt serão
preservados. Colunas não-chave serão atualizadas quando o mesmo ID já existir.
Linhas existentes apenas no cloud permanecerão intactas; não haverá deleção.

A escrita cloud ocorrerá em uma única transação. Qualquer erro provocará rollback.
A conexão local será usada somente para SELECT e será configurada como read-only.
Depois do commit, serão comparadas contagens e a integridade dos relacionamentos.
Uma segunda execução deverá produzir as mesmas contagens e nenhum registro
duplicado.

O relatório padrão mostrará somente nomes de tabela e quantidades. `usuarios`
nunca terá `senha_hash` exibido, nem mesmo com `--verbose`.

## API cloud e CORS

Um comando próprio carregará `.env.mobile`, copiará `CLOUD_DATABASE_URL` para
`DATABASE_URL` apenas no ambiente do processo filho e iniciará a FastAPI. O arquivo
`.env` principal e o ambiente do shell pai não serão alterados.

A configuração da API receberá uma lista validada de origens CORS. O padrão será
lista vazia, preservando o comportamento local. Na PoC, serão permitidas somente
as origens declaradas em `.env.mobile`, como o endereço do servidor web no PC.
Credenciais CORS serão habilitadas porque a aplicação usa cabeçalho Authorization;
métodos e headers permitidos serão limitados aos necessários para login e leitura.

A API cloud continuará usando:

- `POST /auth/admin/login` para autenticação;
- `GET /admin/alerts` e `GET /admin/alerts/{id}` para alertas;
- `GET /health` para saúde.

Nenhum endpoint público ou mecanismo de autenticação adicional será criado.

## Frontend mobile

`2identify_web` conterá HTML, CSS e JavaScript estáticos, executáveis com o servidor
HTTP da biblioteca padrão do Python. A interface terá:

- tela de login administrativo;
- cabeçalho `2IDENTIFY — ALERTAS`;
- cards com severidade, funcionário, operação, setor, mensagem, horário e status;
- indicadores para CRÍTICO, ATENÇÃO e RESOLVIDO;
- filtros Todos, Críticos, Atenção e Resolvidos;
- atualização manual e polling leve;
- estado de carregamento, vazio, erro de conexão e sessão expirada;
- logout que remove imediatamente o token e cancela polling.

O JWT será mantido em `sessionStorage`, nunca em arquivo ou URL. O frontend enviará
`Authorization: Bearer` somente à origem configurada da API. Respostas 401 limparão
a sessão e retornarão ao login.

Referências de imagem ou vídeo serão apresentadas apenas como indicação de
evidência registrada. Caminhos locais não serão publicados como links. A PoC não
criará serviço de arquivos nem copiará evidências biométricas.

## Testes e aceite

O desenvolvimento seguirá TDD. Os testes da API cobrirão:

- configuração cloud separada e segredo mascarado;
- CORS ausente no modo local e explícito no modo mobile;
- nome da operação no contrato existente de alertas;
- preflight contra destino local, host não Supabase, schema conflitante e revisão
  desconhecida;
- bloqueio estático de migrations destrutivas;
- seleção exata das nove tabelas e ordem de Foreign Keys;
- upsert idempotente e rollback em erro;
- ausência de segredos e hashes em saída.

Os testes do frontend usarão funções JavaScript isoladas para filtros, formatação,
polling e logout. A validação integrada executará:

1. preflight cloud mascarado;
2. bootstrap Alembic seguro;
3. sincronização inicial;
4. comparação de contagens e relacionamentos;
5. segunda sincronização idempotente;
6. API contra Supabase;
7. health;
8. login administrativo real;
9. listagem e detalhe de alertas;
10. frontend em viewport 390×844, sem overflow horizontal;
11. polling, filtros e logout.

O teste de login usará credenciais administrativas existentes fornecidas pelo
usuário ou uma sessão já autorizada. Senha de login e JWT nunca serão exibidos.

## Limites

- Não há sincronização contínua entre os bancos.
- Alterações realizadas na API cloud não retornam ao banco local.
- A PoC é destinada a rede de demonstração; publicação na internet exigiria TLS,
  hospedagem, política de origem e gestão de segredos próprias.
- Evidências armazenadas como caminhos locais não são acessíveis pelo celular.
- Não serão alterados Operator, ESP32, Face ID, PPE, Pose, áreas de risco ou
  AlertEngine.
- Não haverá commit ou push nesta entrega.
