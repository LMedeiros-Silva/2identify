# 2Identify Operator

Aplicação desktop do ecossistema 2Identify responsável pelo monitoramento industrial e,
nas próximas etapas, pela orquestração de captura de vídeo, inferência, regras de segurança
e envio de ocorrências para a API.

Este repositório é a raiz independente do **Operator**. Ele não acessa o PostgreSQL
diretamente e não compartilha código-fonte com o projeto Admin.

## Estado atual

O projeto contém a fundação inicial e o fluxo biométrico até a criação da sessão do operador:

- bootstrap único da aplicação;
- configuração tipada carregada do `.env`;
- logging estruturado em console e arquivo rotativo;
- fronteiras de pacotes para domínio, UI, visão, workers, serviços, engine e API;
- objeto de domínio inicial para identidade do funcionário;
- Face ID como acesso principal, com captura e inferência em `QThread` dedicado;
- estados de câmera pronta, inicialização, leitura, reconhecimento, erro e indisponibilidade;
- apresentação do nome, foto cadastrada e mensagem de boas-vindas do operador;
- sessão autenticada imutável, em memória e disponível no contexto da aplicação;
- e-mail/usuário e senha como acesso alternativo via `POST /auth/login`;
- autenticação por credenciais executada em `QThread`, com timeout e falha segura;
- transição autenticada para uma `MainWindow` responsiva e vinculada à sessão;
- shell principal com `QStackedWidget`, pronta para receber os módulos de navegação;
- sidebar reutilizável com rota selecionada, estados hover/pressed e identidade visual;
- página responsiva de Operações com painéis de lista e detalhes;
- estados visuais explícitos para fonte não carregada, carregamento, lista vazia e erro;
- lista dinâmica baseada no domínio `Operation` e carregada por service/provider substituível;
- `MockOperationProvider` isolado, identificado na interface e proibido em produção;
- seleção de operação coordenada pelo controller, com destaque visual exclusivo;
- painel de detalhes preenchido dinamicamente com código, nome, status e descrição;
- relação configurável de EPIs obrigatórios por operação por meio de `PpeRequirement`;
- lista de EPIs renderizada a partir do provider, sem regras condicionais no widget;
- referência tipada para manual local ou URL futura por meio de `OperationManual`;
- abertura segura de PDF local no visualizador padrão, com falhas recuperáveis na interface;
- associação tipada entre operação e área de risco por meio de `RiskAreaReference`;
- polígonos de risco normalizados, validados e independentes da resolução da câmera;
- visualização esquemática da área configurada no painel da operação;
- overlay persistente da zona somente quando a geometria estiver marcada como calibrada;
- engine espacial independente para classificar pontos internos, externos ou na borda;
- ação “Começar trabalho” que abre somente a preparação da verificação de segurança;
- página de verificação com operação, operador, área e EPIs vinculados ao contexto atual;
- câmera operacional capturada em `QThread`, com preview desacoplado de OpenCV na UI;
- ciclo explícito de inicialização, câmera ativa, indisponibilidade, falha e nova tentativa;
- encerramento cooperativo da câmera ao voltar, sair ou fechar a aplicação;
- checkpoint YOLOv8 fornecido carregado em worker de inferência independente;
- frames de análise publicados em cadência própria e substituídos quando ficam obsoletos;
- bounding boxes azuis no preview com classe e confiança de cada detecção bruta;
- transformação correta das caixas para o preview com recorte proporcional e expiração automática;
- vínculo configurável entre cada `PpeRequirement` e a classe correspondente do modelo;
- janela temporal móvel configurável, independente do Qt e do runtime YOLO;
- estados “COLETANDO”, “CONFIRMADO”, “AUSENTE”, “INSTÁVEL” e “SEM MAPEAMENTO”;
- `PpeSafetyEngine` fail-closed para comparar todos os requisitos com a evidência temporal;
- bloqueio para EPI ausente, requisito sem mapeamento, operação inativa ou sem requisitos;
- botão “INICIAR OPERAÇÃO” habilitado somente enquanto a avaliação estiver conforme;
- intenção de início revalidada pelo controller contra operação, câmera e avaliação atuais;
- `WorkSession` local e imutável vinculada a operador, operação, área e EPIs verificados;
- garantia de apenas uma operação ativa por processo, com conclusão ou interrupção explícita;
- tela de operação ativa com contexto real, tempo decorrido e encerramento da sessão;
- monitoramento contínuo de EPIs durante a `WorkSession`, com câmera, YOLO e janela temporal novos;
- bounding boxes brutas e estado estabilizado de cada EPI atualizados na operação ativa;
- tracking class-aware das detecções de EPI, com IDs estáveis e tolerância a perdas breves;
- Alert Engine local com persistência mínima, deduplicação, resolução e cooldown;
- alertas de EPI ausente vinculados à `WorkSession` e identificados como não sincronizados;
- falhas de câmera ou inferência visíveis e tratadas como interrupção do monitoramento;
- logout completo com descarte da sessão e restauração segura do login;
- detecção YuNet e embeddings SFace por OpenCV;
- prova de vida temporal baseline, matching e persistência mínima;
- cadastro local versionado e restrito a desenvolvimento;
- contratos desacoplados para futura autorização e cadastro pela API;
- testes unitários da infraestrutura já implementada.

Tracking de pessoas, avaliação de entrada na área de risco, persistência e sincronização dos
alertas, servidor FastAPI e calibração administrativa ainda não foram implementados. O tracker
atual identifica objetos das classes de EPI do checkpoint; ele não afirma identificar uma pessoa.
Sem um detector de pessoa, a geometria é exibida, mas não produz uma falsa decisão de invasão. A
sessão e os alertas existem somente em memória e o monitoramento não envia dados para serviços
externos.
Em desenvolvimento, o Face ID pode reconhecer operadores cadastrados localmente. Em produção,
essa autorização local é bloqueada e deverá ser substituída pela API.

## Requisitos

- Python 3.11 ou 3.12 (64 bits)
- Windows 10/11 ou Linux com suporte ao Qt 6

## Instalação no Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env -ErrorAction Ignore
python scripts/download_face_models.py
```

O ambiente virtual contém apenas dependências. Todo o código da aplicação permanece fora
de `.venv`.

## Execução

Validar configuração e logging sem abrir a interface:

```powershell
python main.py --check
```

Abrir a aplicação:

```powershell
python main.py
```

Sem câmera, a aplicação continua executando e o acesso alternativo permanece disponível. Ao
iniciar o Face ID sem cadastro biométrico, o fluxo falha antes de tentar abrir a câmera.
Após uma autenticação válida, o login é ocultado e a MainWindow é aberta maximizada com a
identidade e o método de autenticação da sessão atual. A opção `Sair` encerra a sessão em
memória, remove o token quando existir e restaura os dois métodos de login sem dados anteriores.

O acesso alternativo chama a URL configurada em `API_URL`. Se a API estiver offline, demorar
além dos timeouts ou responder fora do contrato, o login permanece bloqueado e a interface
exibe um erro recuperável.

## Contrato atual do login por credenciais

O cliente envia `POST /auth/login` com JSON no seguinte formato:

```json
{
  "username": "operador.15",
  "password": "senha"
}
```

Uma resposta `200` válida deve seguir este contrato mínimo:

```json
{
  "access_token": "token-opaco",
  "token_type": "bearer",
  "operator": {
    "id": 15,
    "name": "João Silva",
    "profile_photo_reference": null
  }
}
```

Respostas `401` e `403` são tratadas como credenciais rejeitadas. Outros erros HTTP, falhas
de rede e payloads inválidos não criam sessão. Senhas e tokens não são registrados em logs.

## Cadastro facial local de desenvolvimento

O comando requer pelo menos três imagens distintas, cada uma contendo exatamente um rosto:

```powershell
python -m app.tools.enroll_operator_face `
  --operator-id 15 `
  --name "João Silva" `
  --image "C:\cadastro\joao-frente.jpg" `
  --image "C:\cadastro\joao-esquerda.jpg" `
  --image "C:\cadastro\joao-direita.jpg"
```

O cadastro é gravado em `var/face_auth`, pasta ignorada pelo Git. Trata-se apenas de uma ponte
para desenvolvimento: os embeddings locais não são a persistência final do produto.

## Testes e qualidade

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m mypy app main.py
```

## Configuração

As configurações locais ficam no arquivo `.env`, que é ignorado pelo Git. O arquivo
`.env.example` documenta todas as variáveis suportadas atualmente. Caminhos relativos,
como `models/best.pt`, são resolvidos a partir da raiz do projeto, independentemente da
pasta usada para iniciar o processo.

Em desenvolvimento, `OPERATIONS_MOCK_ENABLED=true` habilita uma lista local claramente
identificada na interface. Essa fonte existe somente para permitir a evolução da UI antes da
API e a configuração é rejeitada quando `APP_ENVIRONMENT=production`.

`MANUALS_DIRECTORY` define a raiz dos manuais locais. Referências das operações são relativas a
essa pasta e não podem escapar dela. O mock associa à operação “Manutenção industrial” um PDF
demonstrativo explicitamente marcado como sem validade operacional. Operações sem documento
associado mantêm o botão desabilitado e apresentam “Não configurado”.

`CAMERA_SOURCE` configura a câmera da verificação operacional e aceita índice local ou URL de
stream. Resolução, timeouts, limite de leituras inválidas e frequência do preview utilizam as
variáveis `CAMERA_WIDTH`, `CAMERA_HEIGHT`, `CAMERA_OPEN_TIMEOUT_MS`,
`CAMERA_READ_TIMEOUT_MS`, `CAMERA_MAX_FAILED_READS` e `CAMERA_PREVIEW_FPS`. Essa configuração é
independente de `LOGIN_CAMERA_SOURCE` e dos parâmetros da câmera de autenticação.

`PPE_MODEL_PATH` aponta para o checkpoint local (`models/ppe/best.pt`). Confiança, IoU, tamanho
de entrada, cadência e dispositivo são configurados por `PPE_CONFIDENCE_THRESHOLD`,
`PPE_IOU_THRESHOLD`, `PPE_INFERENCE_IMAGE_SIZE`, `PPE_INFERENCE_FPS` e
`PPE_INFERENCE_DEVICE`. O checkpoint fornecido usa Ultralytics YOLOv8 8.4.115 e expõe 11 classes.
O modelo é um artefato local ignorado pelo Git. Configurações auxiliares da biblioteca ficam em
`ULTRALYTICS_CONFIG_DIRECTORY`; o adaptador utiliza o checkpoint em modo offline e não baixa pesos
implicitamente. Antes da desserialização, o arquivo precisa corresponder a `PPE_MODEL_SHA256`.

`PPE_STABILITY_WINDOW_FRAMES` define a janela móvel de observações. A engine não decide antes de
`PPE_STABILITY_MINIMUM_FRAMES`; depois disso, confirma presença acima de
`PPE_STABILITY_PRESENT_RATIO`, confirma ausência abaixo de `PPE_STABILITY_ABSENT_RATIO` e marca a
faixa intermediária como instável. Nos valores padrão, são mantidos oito frames, com pelo menos
cinco amostras e limiares de 75%/25%. Trocar de operação ou interromper a câmera descarta toda a
evidência anterior. `PPE_RELEASE_ASSESSMENT_MAX_AGE_SECONDS` limita por quanto tempo uma avaliação
conforme pode autorizar o início sem receber nova evidência; o padrão é dois segundos. As caixas
visuais usam a mesma validade e desaparecem quando o resultado deixa de ser atual.

Durante a operação ativa, `PPE_TRACKING_IOU_THRESHOLD` controla a associação espacial de caixas da
mesma classe entre inferências. `PPE_TRACKING_MAXIMUM_MISSED_BATCHES` mantém uma identidade durante
perdas curtas e `PPE_TRACKING_MINIMUM_CONFIRMATION_HITS` define quantas associações confirmam o
track. Os padrões são IoU 0,30, até três lotes perdidos e dois acertos. Os IDs são locais à
`WorkSession` e reiniciam ao trocar ou encerrar a sessão.

`ALERT_MINIMUM_CONSECUTIVE_OBSERVATIONS` e `ALERT_MINIMUM_PERSISTENCE_SECONDS` controlam o debounce
antes de criar um alerta local. `ALERT_RESOLUTION_CONSECUTIVE_OBSERVATIONS` exige recuperação
estável e `ALERT_COOLDOWN_SECONDS` impede alertas repetidos após uma resolução. Os padrões são três
observações, 0,75 segundo, três observações de recuperação e 30 segundos de cooldown.

O checkpoint declara licença AGPL-3.0. Esta integração pode ser usada para desenvolvimento sob os
termos aplicáveis, mas uma distribuição proprietária/comercial exige revisão de licenciamento e,
segundo a orientação da fornecedora, uma licença Ultralytics apropriada.

Consulte [docs/architecture.md](docs/architecture.md) para as fronteiras e decisões de
concorrência planejadas e [docs/biometric-authentication.md](docs/biometric-authentication.md)
para o fluxo seguro de autenticação facial.

As origens e licenças dos modelos estão registradas em
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
