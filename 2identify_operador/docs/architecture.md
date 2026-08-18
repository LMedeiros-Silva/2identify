# Arquitetura inicial do 2Identify Operator

## Princípios

1. O Operator é um cliente da FastAPI e nunca conhece credenciais do PostgreSQL.
2. O domínio não importa PySide6, OpenCV, YOLO, bibliotecas de Face ID ou clientes HTTP.
3. A UI apenas apresenta estado e emite intenções; processamento bloqueante não pertence à
   thread principal.
4. Dependências concretas são montadas em `app/bootstrap.py`, evitando singletons dispersos.
5. Configurações dependentes da instalação entram por `.env` e são tipadas em um único lugar.

## Fronteiras de pacotes

```text
main.py
  └── app/bootstrap.py            composição e ciclo de vida
      ├── app/core/               configuração, constantes e logging
      ├── app/ui/                 widgets e apresentação PySide6
      ├── app/services/           casos de uso e orquestração
      ├── app/providers/          fontes substituíveis de dados locais/mock
      ├── app/domain/             regras e objetos sem frameworks
      ├── app/vision/             adaptadores OpenCV/Face ID/YOLO
      ├── app/engine/             conformidade e deduplicação
      ├── app/workers/            limites assíncronos com Qt
      └── app/api/                transporte HTTP e DTOs da API
```

Pacotes ainda não usados possuem apenas `__init__.py`. Isso registra a fronteira sem criar
classes vazias que acabariam virando contratos acidentais.

## Login biométrico

`LoginWindow` é somente uma shell de apresentação e abre `FaceLoginPanel` por padrão. Frames
chegam à view como cópias de `QImage`; nem OpenCV nem o reconhecedor facial são importados
pela UI. O signal `face_login_requested` delega inicialização, captura, prova de vida e matching
ao `FaceLoginController` e ao `FaceAuthenticationWorker`.

`CredentialLoginPanel` é o acesso de contingência e emite `LoginCredentials` por um signal
separado. `CredentialLoginController` cria um `CredentialAuthenticationWorker`, que executa
`AuthService` e `OperatorApiClient` fora da UI thread. A senha é omitida do `repr`, permanece
somente durante a tentativa e nunca é registrada no logging. Respostas da API são validadas
antes de criar uma sessão; falhas de rede, protocolo, autorização ou timeout falham fechadas.
Nenhuma das duas formas de acesso registra credenciais ou templates no logging.

O resultado biométrico usa `OperatorIdentity`, distinto de `EmployeeIdentity`. Isso impede que
o cadastro de uma pessoa monitorada conceda implicitamente acesso à estação Operator. No
ambiente de desenvolvimento, o matching usa um repositório JSON local explicitamente
habilitado. A configuração rejeita essa autorização local em produção, onde a API deverá
confirmar conta, permissões, estação e emitir a sessão.

Veja `docs/biometric-authentication.md` para o fluxo de segurança e implantação.

## Sessão do operador

Um match biométrico válido abre uma `OperatorSession` imutável no
`OperatorSessionContext` mantido pelo `RuntimeContext`. O contexto permite uma única sessão
ativa, recusa substituição implícita e oferece acesso fail-closed aos fluxos protegidos. Ele
é seguro para leitura por futuros workers e permanece estritamente em memória. Em uma sessão
autenticada pela API, ele mantém opcionalmente o bearer token necessário às próximas chamadas,
sempre fora do `repr` e dos logs. A sessão de autenticação é distinta da `WorkSession` industrial
descrita adiante.

O instante de login é normalizado para UTC e o método de autenticação é explícito. No logout
ou encerramento da aplicação, o contexto é limpo; dados biométricos e senhas nunca fazem parte
da sessão.

## Navegação autenticada

O `ApplicationController` recebe os resultados válidos dos dois controllers de login, abre a
sessão e somente então constrói a `MainWindow`. A janela de login é ocultada depois que a shell
principal já está visível, evitando encerrar acidentalmente o processo durante a transição.
Uma segunda autenticação não substitui silenciosamente a sessão nem a janela ativa.

A `MainWindow` recebe um snapshot imutável de `OperatorSession` e não conhece senha, detector
facial ou detalhes do transporte HTTP. Seu `QStackedWidget` é a fronteira de apresentação para
as páginas autenticadas. A rota `works` apresenta uma `OperationsPage` responsiva, dividida em
lista e detalhes. A página começa no estado explícito `NOT_LOADED` e também apresenta
carregamento, dados prontos, lista vazia e erro. Ela recebe objetos `Operation`, renderiza a
coleção dinamicamente e emite somente o identificador quando um item é acionado.

`OperationsController` coordena a view com `OperationService`, que valida identificadores,
filtra operações inativas e depende do contrato `OperationProvider`. Durante o desenvolvimento,
o bootstrap pode montar `MockOperationProvider`; os dados ficam concentrados nessa implementação,
recebem uma identificação visível na interface e são proibidos pela configuração de produção.
O provider atual é somente memória e pode ser consultado imediatamente. Um futuro provider HTTP
deverá executar I/O fora da UI thread antes de ser conectado ao mesmo service.

O controller resolve a intenção de seleção somente contra o snapshot carregado e entrega a
`Operation` correspondente à view. A página mantém um único item destacado e apresenta código,
nome, estado e descrição; seleções desconhecidas são ignoradas e registradas. Ao recarregar ou
entrar em erro, a seleção e os detalhes são descartados para não exibir dados obsoletos. EPIs,
manual, área de risco e a entrada da preparação de segurança fazem parte do painel, sempre a
partir do mesmo snapshot validado.

## EPIs obrigatórios da operação

`PpeRequirement` representa um item do catálogo de EPI por identificador, nome e uma
`detection_class` opcional. `Operation` mantém uma coleção imutável desses requisitos e rejeita
identificadores ou classes de detecção repetidos. Assim, a relação operação/EPI e seu vínculo com
o modelo chegam integralmente pelo provider e nunca dependem de comparações com o nome da operação
na UI ou no service.

Ao selecionar uma operação, o painel renderiza a coleção recebida, a quantidade e um estado
explícito quando nenhum requisito foi configurado. A marca “OBRIGATÓRIO” representa somente a
configuração administrativa; ela não afirma que o equipamento foi detectado ou que a operação
está conforme. A tela de verificação distingue observação de um frame de confirmação temporal.

## Manual da operação

`OperationManual` descreve uma referência sem acoplar o domínio ao sistema de arquivos ou ao Qt.
Referências locais devem ser relativas, terminar em `.pdf` e não podem conter travessia de pasta;
URLs futuras são limitadas a HTTP/HTTPS e não aceitam credenciais embutidas. `Operation` mantém o
manual opcional, permitindo distinguir documento configurado de documento ausente.

`ManualService` recebe `MANUALS_DIRECTORY` e um `ManualLauncher`. Para arquivos locais, ele
resolve o caminho, confirma que permanece abaixo da raiz configurada, exige um arquivo existente
com assinatura PDF e somente então delega a abertura. `DesktopManualLauncher` implementa essa
fronteira com `QDesktopServices`, enquanto os testes utilizam launchers em memória e nunca abrem
programas externos.

A UI emite apenas o identificador da operação. `OperationsController` resolve o manual do
snapshot selecionado, trata falhas sem revelar caminhos locais e registra o resultado. Referências
remotas permanecem modeladas, mas sua abertura está bloqueada até existir o transporte autenticado
da API. O PDF local do provider é um artefato de desenvolvimento claramente identificado como sem
validade operacional.

## Área de risco da operação

`RiskAreaReference` mantém identidade, nome, geometria opcional e o indicador explícito
`geometry_calibrated`. `RiskAreaGeometry` é um polígono simples de `NormalizedPoint`: todas as
coordenadas ficam entre zero e um, independem da resolução, e o domínio rejeita poucos vértices,
área zero, repetição e auto-interseção. Marcar uma área como calibrada sem geometria é inválido.

O painel distingue área ausente, associação sem geometria, geometria demonstrativa e zona
calibrada. `OperationsController` valida a seleção antes de abrir o visualizador esquemático. Os
polígonos do `MockOperationProvider` são deliberadamente demonstrativos e aparecem com aviso de
que não possuem validade operacional. Somente uma geometria marcada como calibrada é convertida em
`CameraRiskZone` e desenhada sobre o preview da `ActiveOperationPage`. A zona é persistente e não
expira junto com as bounding boxes do YOLO.

`RiskAreaSpatialEngine` classifica um ponto normalizado como interno, externo ou sobre a borda do
polígono, com política de borda explícita. A engine não importa Qt, OpenCV ou classes do modelo.
Como o checkpoint atual não detecta pessoas, nenhum ponto corporal é fabricado e nenhuma invasão é
declarada nesta etapa. A futura integração de um detector/tracker de pessoa fornecerá, por exemplo,
o ponto inferior central do indivíduo para essa fronteira espacial.

## Preparação da verificação de segurança

“Começar trabalho” é uma intenção de navegação, não uma confirmação de início da atividade.
`OperationsPage` emite somente o identificador selecionado e `OperationsController` o resolve
contra o snapshot carregado, exige que a operação esteja ativa e publica a `Operation` tipada.
`ApplicationController` liga esse evento à `MainWindow`, que apresenta
`SafetyVerificationPage` dentro do mesmo `QStackedWidget`. Voltar ou selecionar “Trabalhos” na
sidebar retorna à página anterior sem descartar a seleção.

A página recebe a `OperatorSession` já autenticada e a operação validada. Ela apresenta operador,
operação, área de risco e EPIs obrigatórios. Ao ser ativada, emite uma intenção de início para
`SafetyCameraController`, que cria `SafetyCameraWorker` com a câmera operacional configurada.
Inicialização, captura e conversão dos frames ocorrem fora da UI thread; a view recebe somente
`QImage` com memória própria. Ao voltar, sair ou encerrar o processo, o worker recebe cancelamento
cooperativo e libera a câmera.

O preview possui estados explícitos para inicialização, câmera ativa, indisponibilidade e falha,
incluindo nova tentativa. Captura não equivale a inferência ou conformidade; falhas mantêm o fluxo
fechado e o banner “OPERAÇÃO NÃO LIBERADA”.

## Detecção de EPI e estabilidade temporal

`SafetyCameraWorker` publica uma cópia do frame para análise em `PPE_INFERENCE_FPS`, independente
da cadência visual. `PpeInferenceWorker` carrega o modelo fora da UI thread e mantém um único slot
de frame pendente: se a inferência estiver ocupada, uma imagem nova substitui a antiga em vez de
formar uma fila atrasada. `PpeInferenceController` coordena esse ciclo e entrega somente
`PpeDetectionBatch` imutável à engine de estabilidade.

O mesmo lote alimenta um overlay exclusivamente visual no `CameraFrameView`. Cada bounding box é
transformada das coordenadas do frame de análise para o preview com `aspect-fill`, incluindo o
recorte central aplicado pela view. Classe e confiança aparecem sobre caixas azuis. O contrato do
overlay é genérico e Qt-only; ele não conhece Ultralytics nem OpenCV. As caixas expiram se um novo
resultado não chegar e a tela as identifica como observações brutas do frame, nunca como prova de
conformidade.

`UltralyticsPpeDetector` é o único módulo que conhece a API Ultralytics. Ele carrega o checkpoint
local somente após validar o SHA-256 configurado, força o runtime offline, executa inferência sem
salvar resultados e normaliza classe, confiança e caixa delimitadora para contratos próprios. O
checkpoint fornecido registra YOLOv8/Ultralytics 8.4.115
e as classes `bota`, `capacete`, `colete_refletivo`, `luva`, `mangote`, `mao_sem_luva`, `mascara`,
`oculos`, `protetor_headset`, `protetor_intra` e `tronco_sem_colete`.

A `PpeStabilityEngine` recebe somente o conjunto de classes observado em cada resultado e mantém
uma janela móvel limitada. Antes do mínimo de amostras, a decisão é “COLETANDO”. Após esse ponto,
as proporções configuradas produzem “CONFIRMADO”, “AUSENTE” ou “INSTÁVEL”. Um positivo isolado não
confirma presença; amostras antigas saem da janela; iniciar, parar ou trocar o contexto descarta
toda a evidência. A engine não importa Qt, OpenCV ou Ultralytics e pode ser testada isoladamente.

A UI traduz somente classes explicitamente associadas em `PpeRequirement.detection_class`; itens
que o modelo não conhece permanecem “SEM MAPEAMENTO”. A apresentação não calcula conformidade:
ela recebe uma avaliação tipada da engine descrita a seguir.

## Safety Engine e gate de liberação

`PpeSafetyEngine` compara todos os `PpeRequirement` da operação com um
`PpeStabilitySnapshot`. O resultado imutável permanece vinculado ao `operation_id` e classifica
cada requisito como coletando, confirmado, ausente, instável ou sem mapeamento. A decisão geral é
fail-closed: operação inativa, lista vazia, ausência confirmada ou falta de mapeamento bloqueiam;
evidência ainda variável mantém a decisão pendente; somente todos os requisitos confirmados
produzem `COMPLIANT`.

Nesse estado a tela apresenta “VERIFICAÇÃO CONCLUÍDA” e habilita “INICIAR OPERAÇÃO”. O clique não
confia apenas no estado visual: `PpeInferenceController` exige câmera ativa, modelo pronto,
operação correspondente e a avaliação conforme mais recente antes de emitir a intenção tipada de
início. Qualquer novo resultado não conforme, falha, interrupção ou mudança de contexto revoga o
gate. Avaliações também expiram após `PPE_RELEASE_ASSESSMENT_MAX_AGE_SECONDS` sem nova evidência e
a autorização é de uso único. Nenhuma chamada à API ou ao banco ocorre nesse gate.

## WorkSession local e operação ativa

O clique autorizado produz `OperationStartAuthorization`, contendo operação, EPIs verificados,
tamanho da janela, amostras e horário. `WorkSessionService` revalida a idade da autorização e a
cobertura exata dos requisitos antes de criar uma única `WorkSession` ativa. O snapshot imutável
vincula UUID local, operador, operação, área de risco, evidência inicial e horários; `camera_id`
permanece ausente enquanto a API ainda não fornecer uma identidade administrativa para a câmera.

`ApplicationController` encerra a preparação, solicita a liberação da câmera e do worker de
inferência daquela tela e apresenta `ActiveOperationPage`. A sessão ativa possui controladores
próprios para iniciar uma nova captura e um novo worker YOLO, evitando reutilizar a evidência que
autorizou o início. Uma nova `PpeStabilityEngine` começa vazia e atualiza continuamente o estado de
cada EPI obrigatório. O preview exibe as bounding boxes brutas com expiração, enquanto o painel de
estado mostra apenas a decisão temporal estabilizada. Falha de câmera ou inferência deixa o
monitoramento explicitamente interrompido; a câmera faz tentativas limitadas de recuperação e
também oferece nova tentativa manual.

### Tracking das detecções de EPI

`PpeDetectionTracker` fica entre o lote bruto do YOLO e o overlay da operação ativa. Ele associa
caixas somente quando pertencem à mesma classe e atingem o IoU mínimo configurado, aplica vínculo
um-para-um determinístico e publica `PpeTrackingBatch` imutável. Cada `PpeTrackSnapshot` carrega
identidade local, quantidade de acertos, idade, lotes perdidos e estado de confirmação. Tracks são
retidos por uma quantidade limitada de perdas para suportar oclusões breves e são descartados ao
parar a câmera, falhar a inferência ou encerrar a `WorkSession`.

O tracking não altera silenciosamente a decisão de segurança: `PpeStabilityEngine` continua
consumindo as observações brutas e aplica sua própria janela. Os IDs rastreados alimentam o overlay
e formam uma base para deduplicação futura. Como o checkpoint atual possui classes de EPI, mas não
uma classe de pessoa, esta etapa não implementa nem anuncia tracking de funcionário. Um detector
compatível poderá ser conectado posteriormente por um contrato separado.

“Encerrar operação” para os workers, cria um novo snapshot `COMPLETED` e retorna à lista. Logout ou
término do processo também encerra os recursos e converte uma sessão aberta em `INTERRUPTED`. O
serviço mantém somente a sessão atual e o último snapshot encerrado em memória. Nesta etapa não há
tracking de pessoas, avaliação da área de risco, persistência ou sincronização; essas serão
responsabilidades das próximas integrações e da futura API/outbox. Alertas locais descritos abaixo
também são descartados com o ciclo do processo e não representam registros no servidor.

## Sidebar e logout

`Sidebar` é um componente de apresentação orientado a identificadores de rota. Ele mantém o
estado visual selecionado e emite `route_requested`, mas não troca páginas diretamente. A
`MainWindow` traduz a rota para seu `QStackedWidget`, preservando a separação entre navegação e
widgets de conteúdo. Atualmente somente `works`/“Trabalhos” está registrado; novas entradas
podem seguir o mesmo contrato sem alterar o estilo das existentes.

“Sair” emite um signal separado para o `ApplicationController`. O controller limpa a
`OperatorSession`, incluindo o token em memória, fecha a MainWindow e restaura a LoginWindow.
O reset remove frames, identidade apresentada, usuário, senha, erros e estados desabilitados,
permitindo que outro operador autentique sem herdar dados da sessão anterior.

## Concorrência

O login biométrico já executa captura e inferência em um `FaceAuthenticationWorker` dedicado.
O login por credenciais executa I/O HTTP em um `CredentialAuthenticationWorker` separado.
Captura e inferência já possuem limites assíncronos separados. A evolução para regras e
sincronização continua seguindo esta separação:

```text
UI thread
  ├── SafetyCameraWorker em QThread captura e publica o preview controlado
  ├── PpeInferenceWorker em QThread consome somente o frame mais recente
  └── ApiWorker em QThread          realiza I/O e sincroniza uma outbox
```

- A câmera configura buffer pequeno quando o backend oferece suporte e publica frames na cadência
  de preview configurada. Baixa latência é mais importante que processar uma fila atrasada.
- YOLO e Face ID possuem cadências configuráveis e não executam em todos os frames. A estabilidade
  temporal e o tracking leve consomem resultados normalizados; regras operacionais permanecem em
  etapas próprias.
- Sinais enviados à UI carregarão DTOs imutáveis ou imagens já convertidas; widgets nunca
  serão acessados diretamente por workers.
- O Alert Engine e seu signal de saída ficam fora do worker de inferência. Uma futura outbox SQLite
  consumirá somente eventos já deduplicados e permitirá
  continuar detectando durante indisponibilidade da API.

O worker de câmera não executa Face ID nem YOLO; o worker de inferência não captura câmera e não
acessa widgets. Essa separação permite trocar o runtime do modelo sem alterar a apresentação.

## Alertas e repetição

`AlertEngine` recebe o conjunto completo de `SafetyViolation` observado em cada ciclo e mantém uma
máquina de estado por chave de deduplicação. Uma violação precisa atingir quantidade consecutiva e
tempo mínimo antes de levantar um único `SafetyAlert`. Enquanto a condição continua ativa, novos
frames não criam alertas. A ausência da condição precisa persistir por ciclos configuráveis para
resolver a ocorrência; uma recorrência posterior respeita cooldown antes de gerar nova identidade.

`SafetyAlert` vincula UUID local, `WorkSession`, operador, operação, câmera/área quando disponíveis,
tipo, severidade e horários de primeira observação, abertura e resolução. Atualmente
`ActivePpeMonitoringController` traduz somente requisitos estabilizados como `ABSENT` em violações
`PPE_ABSENT` críticas. Estados coletando, instável ou sem mapeamento não são transformados em
ocorrências. A página exibe quantidade e última condição com os rótulos “LOCAL” e “NÃO
SINCRONIZADO”.

O controller publica `local_alert_update_ready` apenas quando há abertura ou resolução, criando a
fronteira para a próxima camada sem executar transporte. Nenhum alerta é enviado, persistido ou
associado a imagem nesta etapa. A decisão permanece independente de HTTP, banco e UI, permitindo
testar offline e conectar posteriormente API/outbox sem alterar a inferência.
