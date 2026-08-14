# 2Identify Operator

Aplicação desktop do ecossistema 2Identify responsável pelo monitoramento industrial e,
nas próximas etapas, pela orquestração de captura de vídeo, inferência, regras de segurança
e envio de ocorrências para a API.

Este repositório é a raiz independente do **Operator**. Ele não acessa o PostgreSQL
diretamente e não compartilha código-fonte com o projeto Admin.

## Estado atual

O projeto contém a fundação da Etapa 1 e a **Etapa 2.1 — autenticação biométrica local**:

- bootstrap único da aplicação;
- configuração tipada carregada do `.env`;
- logging estruturado em console e arquivo rotativo;
- fronteiras de pacotes para domínio, UI, visão, workers, serviços, engine e API;
- objeto de domínio inicial para identidade do funcionário;
- Face ID como acesso principal, com captura e inferência em `QThread` dedicado;
- estados de câmera pronta, inicialização, leitura, reconhecimento, erro e indisponibilidade;
- apresentação do nome, foto cadastrada e mensagem de boas-vindas do operador;
- e-mail/usuário e senha como acesso alternativo;
- detecção YuNet e embeddings SFace por OpenCV;
- prova de vida temporal baseline, matching e persistência mínima;
- cadastro local versionado e restrito a desenvolvimento;
- contratos desacoplados para futura autorização e cadastro pela API;
- testes unitários da infraestrutura já implementada.

YOLO, regras, autenticação pela API e navegação para a MainWindow ainda não foram implementados.
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

Abrir a janela de login biométrico:

```powershell
python main.py
```

Sem câmera, a aplicação continua executando e o acesso alternativo permanece disponível. Ao
iniciar o Face ID sem cadastro biométrico, o fluxo falha antes de tentar abrir a câmera.

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

Consulte [docs/architecture.md](docs/architecture.md) para as fronteiras e decisões de
concorrência planejadas e [docs/biometric-authentication.md](docs/biometric-authentication.md)
para o fluxo seguro de autenticação facial.

As origens e licenças dos modelos estão registradas em
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
