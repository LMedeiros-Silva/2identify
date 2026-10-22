# Autenticação facial do operador

## Objetivo

O reconhecimento facial é a forma principal de acesso ao 2Identify Operator. E-mail/usuário
e senha permanecem como contingência quando câmera, rede ou biometria falharem.

O Face ID do **operador** é um contexto de autenticação separado do Face ID de **funcionários
monitorados**. Os dois não compartilham permissões automaticamente.

## Fluxo implementado

```text
LoginWindow (UI thread)
    ↓ solicita leitura
FaceLoginController
    ↓ cria e controla tentativa
FaceAuthenticationWorker (QThread)
    ├── OpenCVCameraSession → QImage para preview
    └── FaceAuthenticationPipeline
           ├── YuNetFaceDetector
           ├── MotionChallengeLivenessVerifier
           ├── SFaceEncoder
           └── quadros consecutivos → POST /auth/face (token da estação)
    ↓
API: compara com os templates do Admin, exige o mesmo funcionário em todos os quadros
     e vantagem mínima sobre os demais, e emite o token do funcionário
    ↓
CredentialAuthenticationResult (sessão da API)
    ↓
LoginWindow → "Funcionário identificado pela API"
    ↓
OperatorSession → MainWindow
```

A UI não importa OpenCV e o worker nunca acessa widgets. A câmera e os modelos são criados
dentro do `QThread`. O encerramento é cooperativo e ocorre ao cancelar, fechar o programa,
atingir timeout ou concluir o reconhecimento.

## Cadastro e autorização

O cadastro facial é feito no Admin e gravado pela API em `funcionario_face_templates`. Os
templates não saem da API: o Operator envia somente os embeddings dos quadros capturados,
autenticado pelo `OPERATOR_STATION_TOKEN`, que identifica a estação e nunca a pessoa. Sem
esse token, sem API ou com resposta inválida, o Face ID falha fechado e o login por senha
continua disponível. Não existe mais autorização facial local.

## Prova de vida

O componente atual exige movimento facial normalizado durante um intervalo mínimo e falha
fechado até observar o desafio. Isso é melhor que aceitar um frame estático, mas **não é uma
solução anti-spoofing certificada**: vídeo em tela ou ataques mais sofisticados ainda podem
contorná-lo. O adapter deve ser substituído ou validado com profundidade/IR ou um modelo
anti-spoofing adequado ao hardware escolhido.

## Configurações principais

```env
LOGIN_CAMERA_SOURCE=0
LOGIN_CAMERA_WIDTH=1280
LOGIN_CAMERA_HEIGHT=720
FACE_AUTH_ENABLED=true
FACE_AUTH_TIMEOUT_SECONDS=15
FACE_DETECTOR_MODEL_PATH=models/face_detection_yunet_2023mar.onnx
FACE_RECOGNITION_MODEL_PATH=models/face_recognition_sface_2021dec.onnx
OPERATOR_STATION_TOKEN=
FACE_AUTH_MODEL_ID=opencv_sface_2021dec
FACE_AUTH_DETECTION_THRESHOLD=0.90
FACE_AUTH_INFERENCE_FPS=8
FACE_AUTH_PREVIEW_FPS=20
FACE_AUTH_MIN_CONSECUTIVE_MATCHES=3
FACE_AUTH_LIVENESS_REQUIRED=true
```

O limiar de similaridade (`FACE_AUTH_SIMILARITY_THRESHOLD=0.50`) e a margem contra o segundo
funcionário (`FACE_AUTH_AMBIGUITY_MARGIN=0.05`) ficam na API. O limiar `0.50` é uma
configuração inicial específica do SFace. Ele deverá ser calibrado com
operadores, iluminação e câmeras representativos antes de qualquer implantação.

## Funcionamento sem câmera

- modelos, liveness, pipeline, cliente da API, QThread e UI são testáveis sem hardware;
- um arquivo de vídeo pode ser configurado em `LOGIN_CAMERA_SOURCE` durante desenvolvimento;
- vídeo gravado não valida anti-spoofing;
- sem token da estação, a tentativa encerra antes de abrir a câmera;
- sem câmera, o fallback por credenciais continua disponível.

## Requisitos antes de produção

1. Cadastro biométrico controlado pelo Admin/API e associado apenas a operadores ativos.
2. Autorização pela API com conta, função, estação e sessão/token válidos.
3. Proteção de templates em armazenamento e trânsito, com acesso mínimo necessário.
4. Anti-spoofing validado para o hardware e cenário industrial escolhidos.
5. Calibração documentada de falso aceite e falsa rejeição.
6. Limite de tentativas, cooldown e auditoria sem imagens, templates, senhas ou tokens em logs.
7. Política de retenção, privacidade e tratamento de biometria definida com o cliente.
8. Política separada e segura caso autenticação offline seja necessária.

## Próxima evolução

1. substituir/validar prova de vida com a câmera escolhida;
2. testar múltiplos rostos, câmera ausente, baixa luz, capacete, óculos e spoofing.
