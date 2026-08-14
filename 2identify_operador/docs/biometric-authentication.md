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
           ├── CosineFaceMatcher
           └── persistência de matches consecutivos
    ↓
OperatorIdentity
    ↓
LoginWindow → foto cadastrada + "Bem-vindo, Nome"
```

A UI não importa OpenCV e o worker nunca acessa widgets. A câmera e os modelos são criados
dentro do `QThread`. O encerramento é cooperativo e ocorre ao cancelar, fechar o programa,
atingir timeout ou concluir o reconhecimento.

## Cadastro atual

`JsonFaceTemplateRepository` é uma ponte somente para `development/testing`. O comando
`app.tools.enroll_operator_face` exige três imagens distintas, detecta exatamente um rosto por
imagem, calcula a média normalizada dos embeddings e salva a foto pública de perfil.

Templates são dados biométricos sensíveis. O JSON local fica em `var/face_auth`, é ignorado
pelo Git e não é a persistência final. `FACE_AUTH_ALLOW_LOCAL_AUTHORIZATION=true` é rejeitado
automaticamente quando `APP_ENVIRONMENT=production`.

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
FACE_AUTH_TEMPLATE_STORE_PATH=var/face_auth/operators.json
FACE_AUTH_MODEL_ID=opencv_sface_2021dec
FACE_AUTH_CONFIDENCE_THRESHOLD=0.50
FACE_AUTH_DETECTION_THRESHOLD=0.90
FACE_AUTH_INFERENCE_FPS=8
FACE_AUTH_PREVIEW_FPS=20
FACE_AUTH_MIN_CONSECUTIVE_MATCHES=3
FACE_AUTH_LIVENESS_REQUIRED=true
FACE_AUTH_ALLOW_LOCAL_AUTHORIZATION=true
```

O limiar `0.50` é uma configuração inicial específica do SFace. Ele deverá ser calibrado com
operadores, iluminação e câmeras representativos antes de qualquer implantação.

## Funcionamento sem câmera

- modelos, repositório, matching, liveness, pipeline, QThread e UI são testáveis sem hardware;
- um arquivo de vídeo pode ser configurado em `LOGIN_CAMERA_SOURCE` durante desenvolvimento;
- vídeo gravado não valida anti-spoofing;
- sem cadastro, a tentativa encerra antes de abrir a câmera;
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

1. substituir o repositório local pelo cliente da API;
2. cadastrar operadores pelo Admin;
3. substituir/validar prova de vida com a câmera escolhida;
4. emitir uma sessão autorizada;
5. navegar para a MainWindow da Etapa 3;
6. testar múltiplos rostos, câmera ausente, baixa luz, capacete, óculos e spoofing.
