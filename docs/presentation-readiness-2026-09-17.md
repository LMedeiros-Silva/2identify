# Prontidão da apresentação — 17/09/2026

## Estado e decisão

- Branch: `codex/esp32-relay-integration`.
- Commit inicial antes desta entrega: `adedc2e`.
- O checkout já continha alterações locais de Admin, multicâmera, IP/USB, testes, recuperação pós-formatação e integração ESP32. Todas foram preservadas. Não houve reset, rebase, checkout destrutivo, push ou perda de dados.
- O PostgreSQL 18 local está ativo. A API autentica como `identify_user` em `identify_db`; `SELECT current_database(), current_user, 1` via SQLAlchemy retornou `identify_db`, `identify_user`, `1`, e `/health` retornou banco conectado.
- A migration Face ID continua **não aplicada** ao banco restaurado: `alembic current -v` = `e4a7b8c9d0e1`, `heads` = `f1b2c3d4e5f6`. O SQL gerado para esse intervalo contém apenas `CREATE TABLE funcionario_face_templates`, o GRANT DML ao `identify_user` e a atualização da revisão Alembic; a revisão foi testada em banco isolado e não contém DROP, TRUNCATE ou DELETE. Nenhuma DDL foi executada no banco restaurado.
- A investigação local identificou o serviço PostgreSQL 18, o role `postgres` administrador e sessões administrativas abertas no pgAdmin. O pgAdmin não guardou a senha do servidor, o método local em `pg_hba.conf` é `scram-sha-256`, e a automação disponível nesta sessão não controla a janela nativa do pgAdmin. `identify_user` não possui `CREATE` em `public`. Não alterei HBA, ownership ou privilégios globais para contornar a autenticação. Aplicar a migration exige credencial ou acesso administrativo à sessão pgAdmin; é bloqueio externo de acesso, não erro na migration.
- Não há configuração Supabase real acessível após busca de `.env.mobile`, demais `.env`, variáveis de processo, arquivos de configuração e servidores registrados no pgAdmin. O preflight cloud termina com `MobilePocConfigurationError`. Nenhuma escrita ou migration ocorreu no Supabase.
- **Um commit local foi criado**, com as suítes e smoke tests aprovados. O push ao GitHub não foi concluído: Git Credential Manager solicitou autenticação interativa indisponível nesta sessão; o remoto continuou em `adedc2e`. Nenhum force push, merge ou rebase foi realizado.

## Capacete, PPE e Pose

- O detector PPE existente e o Pose COCO existente alimentam `HelmetPlacementEngine`. A região de cabeça usa face e distância entre ombros como escala; a região de mãos usa punhos. Cada capacete é atribuído somente quando uma pessoa vence a comparação geométrica sem ambiguidade.
- A saída por pessoa e câmera é `NA_CABECA`, `NA_MAO` ou `INDETERMINADO`. Há estabilidade temporal mínima de três observações configuráveis, com trilhas locais por câmera e limpeza em troca de geração, frame incompatível, pose ausente ou câmera offline. Não há triangulação nem fusão multicâmera improvisada.
- Para capacete obrigatório, `NA_CABECA` confirma o requisito; `NA_MAO` bloqueia; `INDETERMINADO` mantém `UNKNOWN`/coleta. A mera não detecção continua sem provar ausência. O restante dos EPIs mantém a lógica existente.
- O pré-monitoramento e o monitoramento ativo usam Pose, PPE e a avaliação de segurança existentes. A UI mostra “NA CABEÇA”, “NA MÃO” ou “VERIFICANDO”. Uma violação da câmera secundária conserva seu `camera_id` ao chegar aos alertas; a câmera primária legada continua disponível ao ESP32.
- Testes sem hardware cobrem cabeça, mão esquerda/direita, distância, pose incompleta ou de baixa confiança, duas pessoas, dois capacetes, não atribuição entre pessoas, isolamento entre câmeras, estabilidade, offline, indeterminado e gate de conformidade. As suítes de multicâmera também cobrem seleção, IP/USB, reconexão, latest-frame-wins, justiça do scheduler, áreas de risco e limpeza.
- Teste físico pendente: calibrar limiares geométricos e ângulos com pessoas, EPI e câmeras reais. O Pose atual não fornece um track ID persistente; a associação temporal usa proximidade da cabeça por câmera e deve ser validada em cruzamentos/oclusões reais.

## Relatórios Excel

- A rota “Relatórios” do Admin agora gera `.xlsx` válido com `openpyxl`, consumindo a API autenticada e suas páginas de `/admin/alerts`; o desktop não acessa PostgreSQL diretamente.
- Planilhas: `Resumo`, `Alertas`, `Ocorrências` vinculadas aos alertas e `EPIs` vinculados aos alertas de PPE. Incluem câmera e ID corretos, funcionário, setor, operação, severidade, status, observação e datas UTC; cabeçalhos, autofilter, colunas dimensionadas e cabeçalho congelado. Texto externo é protegido contra fórmula de planilha.
- Filtros disponíveis: datas inicial/final, IDs de setor/funcionário/operação/câmera e severidade. Não há relatório de todas as ocorrências sem alerta, inventário de EPI ou duração de operação porque o endpoint atual de alertas não fornece esses conjuntos completos.
- Testes abrem o workbook com `openpyxl`, validam páginas, filtros, acentos, datas, arquivo vazio, várias câmeras, identidade e integração da tela/cliente.

## Funcionários e Face ID no Admin

- Foi criada a tela de funcionários integrada à API para cadastrar, editar, ativar/desativar, selecionar setor, cargo/função e turno. A `matricula` é obrigatória porque a tabela restaurada já a exige; CPF e email não existem no modelo atual.
- O fluxo de Face ID captura frontal, esquerda e direita pela webcam em worker Qt, valida exatamente um rosto, confiança, tamanho, nitidez, luz e orientação, permite repetir, combina embeddings normalizados de YuNet/SFace e envia o template à API. Modelos reais carregaram sem câmera após correção para caminho Unicode do Windows. Os testes usam webcam/modelos falsos e verificam liberação do dispositivo e falhas de captura/API.
- A API oferece CRUD autenticado de funcionários e gravação/consulta de metadados do template. Não devolve o embedding no endpoint de consulta. O template de funcionário é distinto do Face ID de login do Operator; não houve Face ID → JWT. A captura gera template, sem persistir foto de perfil — armazenamento central de foto permanece uma evolução separada.
- Migration `f1b2c3d4e5f6` **criada, não aplicada**: somente cria `funcionario_face_templates`, com FK para `funcionarios` e GRANT mínimo à conta da API. Downgrade destrutivo é bloqueado. Teste isolado provou preservação de funcionários existentes, gravação e recuperação do template via API; captura frontal/esquerda/direita no Admin é testada com webcam/modelos falsos. No banco restaurado a tabela ainda está ausente, logo a persistência central real do Face ID continuará indisponível até uma sessão administrativa aplicar a migration. CRUD de funcionários não depende dessa tabela.
- Nenhum dado do banco restaurado foi alterado neste trabalho.

## Alertas, Supabase e mobile

- O frontend mobile existente continua autenticando pela API e lendo `/admin/alerts`. Agora pagina todos os alertas e mostra nome da câmera, além de mensagem, data/hora, severidade, funcionário e status. A PoC permanece com API intermediária; o PostgreSQL local principal não foi substituído.
- O bootstrap Supabase foi fixado na revisão cloud já aprovada `e4a7b8c9d0e1`; a nova migration de biometria não é aplicada à cloud por um `upgrade head` acidental. Os testes da auditoria/migração da PoC passaram.
- Um alerta sintético identificável foi criado via `/operator/alerts` e recuperado via `/admin/alerts` com autenticação real **em banco isolado de teste**. Foram verificados texto, severidade, status, data e câmera. Nenhum alerta sintético foi escrito no banco restaurado ou no Supabase.
- `CLOUD_DATABASE_URL` não está configurada localmente e nenhuma credencial cloud foi encontrada. Portanto conectividade, autenticação, schema, escrita/sincronização, leitura e exibição no dispositivo contra o Supabase real **não foram validados**. Não foi criado alerta real na cloud; o alerta sintético foi somente no banco isolado de teste. O sync cloud existente é manual e protegido por preflight; não se declara sincronização em tempo real. Teste no celular físico e URL/rede da apresentação: **pendentes**.
- Frontend estático: 10 testes Node aprovados; `index.html`, `app.js` e `alerts.js` responderam HTTP 200 no smoke local. Não há etapa de build no projeto.

## Cadastro de câmeras e grade multicâmera

- O Admin cadastra câmeras por setor via API, com fonte IP (RTSP/HTTP(S)) ou índice USB, sem aceitar credenciais no catálogo. Nesta validação foi completada a manutenção: `GET /admin/cameras` lista ativas e inativas, com filtro opcional `sector_id`; `PUT /admin/cameras/{id}` edita nome, fonte, setor e status. A UI de Operações filtra as câmeras por setor, permite selecionar uma câmera inativa para edição e recarrega o catálogo após salvar. Não houve migration.
- O endpoint de seleção do Operator continua derivando o setor da operação pela câmera da área de risco primária e retornando somente câmeras **ativas** desse setor. A API omite índice USB específico da estação e credenciais RTSP. Se uma câmera legada tiver credenciais embutidas no banco, a API as oculta, e uma edição apenas de metadados não apaga silenciosamente a fonte original; novas fontes com credenciais continuam rejeitadas.
- Testes de UI sem hardware confirmaram 1, 2, 3, 4, 5 e 6 tiles distintos, nome/status próprios, grade rolável, frame A somente no tile A e frame B somente no B. Em quatro tiles, uma câmera OFFLINE permanece visível e as outras seguem ONLINE/atualizando. Após trocar A+B+C por A+D, os tiles B/C desaparecem e sinais atrasados não os recriam. Os testes de 5/6 câmeras confirmam a área de risco só no tile da câmera associada.
- O CameraManager abre apenas a seleção, usa workers independentes com reconexão/backoff, geração de sessão e liberação ao parar. O scheduler PPE usa um único YOLO e latest-frame-wins com justiça entre câmeras; não há fila crescente nem fusão insegura. IP e USB simultâneos, subconjuntos e modo de uma câmera são cobertos pela suíte Operator.
- Nenhum stream RTSP da Metaindústria ou câmera USB física foi aberto nesta sessão. FPS de preview/inferência, CPU, RAM, GPU, latência, codec, reconnect real e ergonomia visual em monitor físico continuam pendentes de teste no local.

## Suítes, integrações e startup

| Módulo | Resultado completo | FAILED | ERROR | SKIPPED |
| --- | ---: | ---: | ---: | ---: |
| Admin | 113 passed | 0 | 0 | 0 |
| API | 186 passed; 1 aviso externo de depreciação Starlette/AnyIO | 0 | 0 | 0 |
| Operator | 352 passed | 0 | 0 | 0 |
| Mobile/web | 10 passed | 0 | 0 | 0 |

- Ruff: aprovado em Admin, API e Operator.
- API: Uvicorn com um worker iniciou, `/health` retornou banco conectado, e o processo foi encerrado. Leitura SQLAlchemy confirmou `identify_db` e `identify_user`.
- Admin: inicialização da UI Qt offscreen e encerramento normais; telas principais são instanciadas nos testes. YuNet/SFace carregaram pelo OpenCV real. Uma primeira tentativa de smoke falhou por passar um argumento incorreto ao wrapper temporário de `QApplication.exec`; corrigido o wrapper, o aplicativo iniciou e encerrou com exit 0. O código do produto não precisou dessa correção.
- Operator: `main.py --check` e UI Qt offscreen iniciaram e encerraram normalmente. O catálogo real da API respondeu com cinco operações ativas e o endpoint de câmeras por operação respondeu sem abrir streams.
- Integrações cobertas por testes: Admin→API (cliente e contratos), Operator→API (catálogo real e alertas em banco isolado), Operator multicâmera→PPE/Pose, PPE/Pose→classificação, alertas→API, funcionários→API→Face ID e relatórios→API→XLSX. A integração cloud real segue bloqueada pela configuração ausente.
- `models/ppe/best.pt` existe localmente, carregou no `UltralyticsPpeDetector`, tem SHA-256 `2EBD001C8AB294D27C184BD78C48236C019BB684D9774455DF0868B4E39F011F` igual ao configurado e contém a classe `capacete` entre 11 classes. O scheduler multicâmera continua usando um detector PPE compartilhado. O checkpoint não foi retreinado nem substituído. O arquivo de 6.254.698 bytes continua excluído pelo `.gitignore` intencional de modelos `.pt`; deve ser copiado manualmente para outro PC.
- ESP32: firmware, GPIO, protocolo, WebSocket e lógica da torre não foram alterados; os testes de safety state/alertas continuam passando. Teste físico da torre pendente.
- Sem hardware/rede da Metaindústria: FPS de preview/inferência, latência, CPU/RAM/GPU e precisão física não puderam ser medidos. Os testes de scheduler verificam troca de frames e justiça sem câmera; a suíte Operator terminou em 13,89 s neste computador, o que não representa desempenho de vídeo real.

## Segurança, Git e pendências

- `.env` da API, Admin e Operator, `.env.mobile` e `best.pt` são ignorados pelo Git. Não foram registrados tokens, senhas, URL de banco completa nem RTSP autenticado neste relatório.
- Varredura dos arquivos versionáveis: nenhum RTSP autenticado, nenhuma senha real de câmera identificada e nenhum `.env` operacional rastreado. Somente URLs fictícias de banco em fixtures de teste foram detectadas, sem credenciais operacionais. Antes do envio, revisar novamente o índice staged e executar `git diff --cached --check`.
- `git diff --check`: aprovado antes da preparação do commit, sem erro de whitespace. Há avisos informativos de conversão LF/CRLF no Windows.
- Correções adicionais: carregamento YuNet/SFace em caminho Unicode; bootstrap cloud preso à revisão aprovada; validação de paginação mobile para evitar lista truncada.
- Foi criado um backup PostgreSQL **somente leitura** em `C:\Users\gokga\Downloads\identify_db_2026-09-17.backup`, 43.033 bytes, validado com `pg_restore --list`, SHA-256 `3DC66ABB68BC9623C6523C0346BB348F437E34CF9156EF4BDF6A027BCD5B0B02`. Contém dados reais, está fora do Git e requer transporte seguro. O [guia do novo PC](new-pc-presentation-setup-2026-09-17.md) traz clone, Python, venvs, requisitos, PostgreSQL, `.env`, Alembic, modelos, fontes por câmera, API/Admin/Operator/mobile, Supabase e ESP32.
- Bloqueadores externos restantes: obter acesso administrativo PostgreSQL para aplicar `f1b2c3d4e5f6` e validar Face ID persistido no banco restaurado; obter `CLOUD_DATABASE_URL` real para preflight/sync e alerta sintético end-to-end no Supabase. Testes físicos de multicâmera, Pose/capacete, USB/IP, celular e ESP32 permanecem pendentes. Nenhuma dessas pendências foi apresentada como teste real aprovado.
- Commit final local: **sim, um commit**. O hash do commit é gerado a partir deste próprio arquivo, portanto não pode ser gravado nele sem alterá-lo; consulte `git log -1 --format=%H` neste checkout. Push: **não**, bloqueado por autenticação GitHub inexistente no terminal desta sessão. HEAD remoto confirmado por `git ls-remote`: `adedc2efc098e475636ab137762ae4c1c23c3892`. O checkout local está limpo, um commit à frente. Não foi feito force push, merge ou rebase. Um Git bundle portátil do commit foi preparado fora do repositório como alternativa para o novo PC; veja o guia.
