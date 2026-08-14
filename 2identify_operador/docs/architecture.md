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
separado. A senha é omitida do `repr` e nunca é registrada no logging. Nenhuma das duas formas
de acesso registra credenciais ou templates no logging.

O resultado biométrico usa `OperatorIdentity`, distinto de `EmployeeIdentity`. Isso impede que
o cadastro de uma pessoa monitorada conceda implicitamente acesso à estação Operator. No
ambiente de desenvolvimento, o matching usa um repositório JSON local explicitamente
habilitado. A configuração rejeita essa autorização local em produção, onde a API deverá
confirmar conta, permissões, estação e emitir a sessão.

Veja `docs/biometric-authentication.md` para o fluxo de segurança e implantação.

## Concorrência

O login biométrico já executa captura e inferência em um `FaceAuthenticationWorker` dedicado.
Para o monitoramento, o fluxo recomendado continua sendo:

```text
UI thread
  ├── CameraWorker em QThread       captura e publica o frame mais recente
  ├── InferenceWorker em QThread    consome frames em frequência controlada
  └── ApiWorker em QThread          realiza I/O e sincroniza uma outbox
```

- A câmera terá buffer pequeno e política de descarte de frames antigos. Em monitoramento ao
  vivo, baixa latência é mais importante que processar uma fila atrasada.
- YOLO e Face ID terão cadências configuráveis e poderão compartilhar tracking entre
  inferências, sem obrigar execução em todos os frames.
- Sinais enviados à UI carregarão DTOs imutáveis ou imagens já convertidas; widgets nunca
  serão acessados diretamente por workers.
- O envio de alerta ficará fora do worker de inferência. Uma futura outbox SQLite permitirá
  continuar detectando durante indisponibilidade da API.

Detalhes de QThread e backpressure serão fechados na Etapa 6, depois que o comportamento real
da câmera for conhecido na Etapa 5.

## Alertas e repetição

O futuro `AlertEngine` deverá compor uma chave estável de situação (pessoa/tracking, área,
tipo e EPI), exigir persistência mínima por frames/tempo e aplicar cooldown. A decisão de
conformidade ficará separada do transporte HTTP, permitindo testar regras offline e trocar a
estratégia de sincronização sem alterar a IA.
