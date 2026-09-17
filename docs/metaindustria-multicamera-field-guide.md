# Ensaio multicâmera na Metaindústria

Estado em 17/09/2026: o checkpoint PPE novo foi carregado no Python do Operator, a suíte do Operator passou (328 testes), e o desktop abriu e fechou normalmente. O computador está fora da rede `10.14.x.x`; as cinco portas RTSP testadas não responderam. Nenhuma USB foi detectada nos índices 0–5. O cadastro físico foi reservado para a demonstração no Admin, conforme decisão do responsável; por isso, os IDs reais e os vínculos de setor ainda não existem.

A consulta somente em leitura ao `identify_db` encontrou apenas estes registros de câmera, que não identificam as seis fontes físicas planejadas:

| ID | Nome existente | Setor | Ativa | Tipo derivado |
|---:|---|---:|---|---|
| 1 | Camera de Teste | 3 — Manutenção | Sim | USB |
| 2 | Camera teste | 2 — Almoxarifado | Sim | USB |

As operações 1, 4 e 5 usam áreas ligadas à câmera 1; as operações 2 e 3 usam área ligada à câmera 2. Nenhuma câmera física da Metaindústria foi cadastrada nesta preparação.

## Preparação já feita e vínculo após o cadastro

As fontes RTSP privadas estão somente em `2identify_operador/.env`, sob `CAMERA_STAGED_FRESA_1`, `CAMERA_STAGED_FRESA_2`, `CAMERA_STAGED_TENDA`, `CAMERA_STAGED_SALA_4` e `CAMERA_STAGED_SICK`. Esses nomes são **preparação local**: o Operator só abre uma câmera catalogada quando encontrar `CAMERA_SOURCE_<camera_id>` ou uma fonte pública utilizável. Não copiar a fonte autenticada para o Admin, banco, `.env.example`, documentação ou logs.

No Admin, cadastrar cada IP com nome, setor escolhido na demonstração e endereço **sem usuário, senha ou query string**. Para as quatro câmeras com caminho `realmonitor`, o endereço público pode ser `rtsp://HOST:554/cam/realmonitor`; a fonte privada completa, com os parâmetros necessários, já está no `.env` local. Para a SICK, o endereço público é `rtsp://10.14.22.96:554/video`. Para USB, cadastrar um índice numérico como representação do tipo; o índice efetivo desta estação será vinculado localmente após a sondagem. Verificar duplicidades antes de salvar.

O catálogo do Operator deriva o setor da operação por sua **câmera da área de risco primária**. As câmeras recém-cadastradas só aparecem na seleção da operação se estiverem no mesmo setor dessa câmera. Hoje as operações associadas à câmera primária 1 pertencem ao setor 3 (Manutenção), e as associadas à câmera primária 2 pertencem ao setor 2 (Almoxarifado). Caso a demonstração escolha outro setor, configurar no Admin uma operação/área apropriada antes do teste de seleção. A área de risco de uma operação continua válida somente para sua câmera original; selecionar outras câmeras não transfere o polígono.

Depois de salvar os cadastros, consultar apenas ID, nome e setor de `cameras` no banco ou no catálogo administrativo. Não imprimir `endereco`. No diretório `2identify_operador`, vincular cada fonte com o ID **real** recebido no cadastro:

```powershell
.\.venv\Scripts\python.exe scripts\bind_camera_sources.py --camera "FRESA_1=ID_REAL"
.\.venv\Scripts\python.exe scripts\bind_camera_sources.py --camera "FRESA_2=ID_REAL"
.\.venv\Scripts\python.exe scripts\bind_camera_sources.py --camera "SICK=ID_REAL"
```

Substituir `ID_REAL` pelo número positivo real; repetir para `TENDA` e `SALA_4` depois de cadastradas. O utilitário lê as fontes privadas já preparadas, grava `CAMERA_SOURCE_<id>` no `.env` ignorado e imprime só `CONFIGURADO`. Ele recusa sobrescrever um vínculo diferente sem `--replace`. Depois de conectar a USB, usar `scripts\probe_usb_cameras.py` e vincular o índice real com `--usb "ID_REAL=INDICE_REAL"`. O `CAMERA_SOURCE` global permanece apenas como fallback legado; não usá-lo como substituto dos vínculos por ID.

Para consultar os IDs sem exibir fontes, usar uma ferramenta SQL com a conexão local da API:

```sql
SELECT id, nome, setor_id, ativa FROM cameras ORDER BY id;
```

O cenário inicial é selecionar Fresa 1, Fresa 2 e SICK, acrescentando a USB se disponível. Tenda e Sala 4 podem ficar cadastradas e desmarcadas enquanto offline. Na apresentação seguinte, qualquer subconjunto das cinco IP e da USB pode ser escolhido; somente as selecionadas serão abertas. A SICK entra apenas como vídeo 2D RTSP.

`POSE_CAMERA_IDS` vazio significa Pose nas câmeras selecionadas quando Pose está habilitada. Para restringir Pose, preencher no `.env` local com IDs reais separados por vírgula; não usar IDs de exemplo no arquivo real.

O novo `best.pt` contém as 11 classes listadas no passo 10. Os EPIs cadastrados têm mapeamento existente: `EPI-001` Capacete → `capacete`; `EPI-002` Luvas → `luva`; `EPI-003` Botas → `bota`; `EPI-004` Mangote → `mangote`; `EPI-005` Óculos de proteção → `oculos`; `EPI-006` Protetor auricular → `protetor_headset`. Esta última associação cobre o tipo concha/headset, **não** `protetor_intra`; confirmar o tipo físico antes de cobrar esse requisito. As cinco operações ativas hoje exigem apenas Capacete. As classes negativas do modelo não autorizam, por si só, transformar não-detecção em `ABSENT`.

## Checklist para amanhã

1. Conectar PC/notebook à rede da empresa e confirmar acesso à sub-rede das câmeras.
2. Testar a API (`/health`) e registrar o resultado.
3. Confirmar que o PostgreSQL local e `identify_db` estão acessíveis, sem alterar dados.
4. Testar TCP 554 em Fresa 1 (`10.14.22.97`), Fresa 2 (`10.14.22.98`), Tenda (`10.14.22.99`), Sala 4 (`10.14.24.6`) e SICK (`10.14.22.96`).
5. Conectar a câmera USB própria do projeto.
6. Descobrir seu índice com `cd 2identify_operador; .\.venv\Scripts\python.exe scripts\probe_usb_cameras.py --max-index 5 --frames 3`; o utilitário libera cada dispositivo.
7. Conferir/cadastrar as câmeras no Admin, escolhendo o setor durante a demonstração; verificar a correspondência com a operação.
8. Conferir os `CAMERA_SOURCE_<id>` usando IDs reais e o utilitário `scripts\bind_camera_sources.py`, sem imprimir valores.
9. Validar que `models/ppe/best.pt` existe e que `PPE_MODEL_SHA256` local corresponde ao arquivo.
10. Conferir as 11 classes carregadas: `bota`, `capacete`, `colete_refletivo`, `luva`, `mangote`, `mao_sem_luva`, `mascara`, `oculos`, `protetor_headset`, `protetor_intra`, `tronco_sem_colete`.
11. Testar Fresa 1 isoladamente, sem YOLO primeiro: abertura, primeiro frame, resolução, FPS e liberação.
12. Testar Fresa 2 isoladamente com as mesmas medições.
13. Testar SICK isoladamente como RTSP 2D comum.
14. Testar a USB isoladamente; se falhar, repetir a sondagem e atualizar seu índice local.
15. Testar Fresa 1 + Fresa 2 + SICK + USB simultaneamente **sem YOLO**; medir FPS, intervalos entre frames, CPU, RAM, GPU se disponível, reconexões e fechamento.
16. Testar os mesmos streams com PPE; medir inferência por câmera, idade dos frames e substituições, sem interpretar simples não-detecção como ausência.
17. Iniciar a API pelo comando real do projeto e conferir `/health`.
18. Iniciar o Admin e concluir o cadastro/associação de setor no aplicativo.
19. Iniciar o Operator pelo Python de `2identify_operador/.venv` (`.\.venv\Scripts\python.exe main.py`).
20. Escolher uma operação cujo setor derivado inclua as câmeras cadastradas.
21. Selecionar apenas Fresa 1, Fresa 2, SICK e USB disponível; deixar Tenda/Sala 4 desmarcadas se offline.
22. Iniciar monitoramento e verificar que somente as selecionadas abrem conexões/workers.
23. Conferir nome, imagem e status de cada tile na grade simultânea.
24. Conferir PPE por câmera e os estados `PRESENT`, `ABSENT`, `UNKNOWN`; câmera offline/stale e simples não-detecção devem permanecer `UNKNOWN`.
25. Conferir Pose nas câmeras permitidas por `POSE_CAMERA_IDS`.
26. Conferir que o polígono da área de risco aparece e é avaliado somente na câmera associada.
27. Conferir que alertas mantêm o `camera_id` da evidência real, sem reatribuição à câmera primária.
28. Conferir a integração ESP32 existente, sem alterar firmware, GPIO ou protocolo.

## Diagnóstico rápido

| Problema | Verificação | Ação |
|---|---|---|
| Fresa 1 não abre | TCP `10.14.22.97:554`, vínculo local pelo ID e primeiro frame | Confirmar rede/VLAN, cadastro, ID e fonte local; testar isolada. |
| Fresa 2 não abre | TCP `10.14.22.98:554`, vínculo local pelo ID e primeiro frame | Repetir a checagem isolada para Fresa 2. |
| SICK não abre | TCP `10.14.22.96:554`, caminho `/video` e primeiro frame | Confirmar serviço RTSP da SICK e fonte local, sem tentar SDK/depth. |
| Tenda offline | TCP `10.14.22.99:554`, status no tile | Deixar cadastrada e desmarcada; testar quando a rede/dispositivo estiver disponível. |
| Sala 4 offline | TCP `10.14.24.6:554`, status no tile | Deixar cadastrada e desmarcada; testar quando disponível. |
| USB não abre | Sondagem de índices, uso por outro aplicativo, permissão do Windows | Fechar outro cliente de vídeo, reconectar e sondar novamente. |
| Índice USB mudou | Comparar sondagem atual com `CAMERA_SOURCE_<id>` | Atualizar somente o índice local da estação. |
| Preview preto | Primeiro frame válido, resolução e estado do worker | Testar a fonte sem YOLO; verificar codec, path e VideoCapture. |
| RTSP autenticação falhou | Credenciais locais presentes, resposta do dispositivo | Corrigir apenas o `.env` local; não colar URL autenticada em logs/chamados. |
| Todas IP offline | IP local/VLAN, rota e TCP 554 dos cinco hosts | Conectar à rede da empresa antes de investigar o Operator. |
| Uma câmera caiu | Status/contador de reconexão daquela câmera; demais tiles | Aguardar backoff e reabertura; isolar rede/dispositivo afetado. |
| UI lenta | CPU/RAM/GPU, preview FPS e inferência FPS por câmera | Reduzir resolução/FPS configurados ou subconjunto selecionado; preservar latest-frame-wins. |
| Captura funciona, PPE não | Checkpoint, hash, log de carregamento, classes e inferência | Validar modelo na `.venv`; testar imagem real adequada. |
| `best.pt` não carrega | Arquivo regular, legibilidade, SHA e mensagem da biblioteca | Corrigir caminho/hash de configuração; preservar o checkpoint original. |
| Classes do `best.pt` não correspondem | Comparar `model.names` aos EPIs ativos e aliases | Registrar divergência sem inventar alias semântico. |
| PyTorch falha ao carregar | Traceback e versão na `.venv` do Operator | Reparar dependência/ambiente local; não trocar o modelo sem diagnóstico. |
| Ultralytics falha ao carregar | Traceback, dependências e integridade do checkpoint | Reparar ambiente e repetir teste direcionado. |
| Inferência lenta | FPS/idade do frame analisado, CPU/GPU e número de câmeras | Ajustar cadência/resolução, verificar uso do YOLO único e frames substituídos. |
| Área de risco na câmera errada | `areas_risco.camera_id`, operação e tile receptor | Parar teste e corrigir associação/configuração; não copiar polígono entre câmeras. |
| Alerta com `camera_id` errado | ID do frame, detecção, alerta e payload da API | Parar teste e rastrear identidade em cada estágio; não reatribuir à primária. |
| API offline | `/health`, processo/porta local e log sanitizado | Iniciar/reiniciar API e verificar configuração local. |
| PostgreSQL offline | Serviço PostgreSQL 18, conexão read-only ao `identify_db` | Iniciar serviço/verificar URL local; não restaurar/resetar banco. |
| ESP32 desconectado | Conexão e estados já existentes da torre | Verificar alimentação/rede/serviço; não alterar firmware ou protocolo nesta etapa. |

Os testes locais não substituem captura física. Ainda faltam rede da empresa, câmera USB conectada, IDs reais do cadastro, frames reais, medição de FPS/recursos sob carga e validação de PPE/Pose/alertas/ESP32 em campo.
