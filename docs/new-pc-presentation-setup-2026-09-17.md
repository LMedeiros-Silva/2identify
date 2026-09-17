# Instalação do 2Identify em outro PC

Este guia usa a branch `codex/esp32-relay-integration` e Windows/PowerShell. O clone traz código, migrations, testes, assets, modelos YuNet/SFace e firmware de exemplo. Os arquivos `.env`, o banco, o checkpoint PPE e o modelo público de Pose não vêm do Git. Não copie credenciais para o repositório.

**Estado do envio em 17/09/2026:** o commit está apenas neste PC porque o push pediu autenticação GitHub não disponível. Até o push ser concluído, clonar o remoto sozinho traz a versão anterior. Para transportar a versão desta apresentação sem depender do push, copie o Git bundle da tabela abaixo e use o procedimento alternativo da seção 1.

## Arquivos para transportar com segurança

| Arquivo no PC atual | Uso no novo PC |
| --- | --- |
| `C:\Users\gokga\Downloads\identify_db_2026-09-17.backup` | Backup PostgreSQL custom, 43.033 bytes, SHA-256 `3DC66ABB68BC9623C6523C0346BB348F437E34CF9156EF4BDF6A027BCD5B0B02`. Contém dados do banco; transfira por meio seguro e não versione. |
| `2identify_operador\models\ppe\best.pt` | Copiar para o mesmo caminho relativo no clone. 6.254.698 bytes, SHA-256 `2EBD001C8AB294D27C184BD78C48236C019BB684D9774455DF0868B4E39F011F`. O Git o ignora. |
| `C:\Users\gokga\Downloads\2identify-presentation-2026-09-17.bundle` | Histórico Git e commit local da apresentação, caso o push continue bloqueado. Verifique com `git bundle verify` antes de clonar. Não contém `.env`, backup nem `best.pt`. |
| Configurações locais `.env` | Recriar a partir dos exemplos no novo PC; transportar segredos somente por canal privado. Índices USB são próprios de cada estação. |

O backup foi validado com `pg_restore --list`, sem executar restore neste PC. O arquivo SQL anterior no Desktop não substitui esse backup mais recente.

## 1. Clone e dependências

Instale Git, Python 3.12 de 64 bits e PostgreSQL 18. Node.js é necessário apenas para os testes do frontend; a página mobile é estática. **Se o push já estiver no remoto**, clone pelo GitHub:

```powershell
git clone --branch codex/esp32-relay-integration https://github.com/LMedeiros-Silva/2identify.git 2identify
Set-Location -LiteralPath .\2identify
git branch --show-current
```

**Enquanto o push estiver bloqueado**, use o bundle transportado em vez do clone remoto:

```powershell
git clone --branch codex/esp32-relay-integration 'CAMINHO_DO_BUNDLE.bundle' 2identify
Set-Location -LiteralPath .\2identify
git remote set-url origin https://github.com/LMedeiros-Silva/2identify.git
```

Depois de escolher **um** dos métodos de clone, prepare as venvs:

```powershell
Set-Location .\2identify_api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Set-Location ..\2identify_admin
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Set-Location ..\2identify_operador
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\download_pose_model.py
```

O PowerShell pode bloquear `Activate.ps1`; chamar `python.exe` diretamente evita mudar a ExecutionPolicy. Copie o `best.pt` para `models\ppe\best.pt` e confira `(Get-FileHash .\models\ppe\best.pt -Algorithm SHA256).Hash` com o valor acima. Os modelos faciais versionados já estarão no clone; `scripts\download_face_models.py` verifica/recupera esses modelos se necessário.

## 2. Banco local em uma instalação nova

Use uma conta administrativa do PostgreSQL 18. **Estes passos de criação/restauração são apenas para um PC novo com banco vazio; nunca os execute no `identify_db` restaurado do PC atual.** Prepare o role `identify_user` como conta de runtime, sem SUPERUSER, CREATEDB ou CREATEROLE. No `psql` administrativo:

```sql
CREATE ROLE identify_user LOGIN;
\password identify_user
CREATE DATABASE identify_db OWNER postgres;
```

`\password` solicita a senha sem incluí-la no histórico. Em um PowerShell novo, restaure o arquivo transportado no banco **vazio** com PostgreSQL 18:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' --exit-on-error --no-owner --no-privileges -U postgres -d identify_db 'CAMINHO_SEGURO_DO_BACKUP.backup'
```

No `psql` conectado como administrador a `identify_db`, conceda somente o acesso de runtime:

```sql
GRANT CONNECT ON DATABASE identify_db TO identify_user;
GRANT USAGE ON SCHEMA public TO identify_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO identify_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO identify_user;
```

O backup registra a revisão Alembic `e4a7b8c9d0e1`. A revisão aditiva de Face ID `f1b2c3d4e5f6` cria somente `funcionario_face_templates` e concede DML ao `identify_user`. Verifique `alembic current -v`, `heads` e a migration antes de aplicar. Aplique **como administrador**, nunca dando DDL permanente ao role de runtime. A partir de `2identify_api`, o bloco abaixo pede a senha sem eco e mantém a URL administrativa apenas no processo Python:

```powershell
@'
import getpass
import os
from urllib.parse import quote
from alembic import command
from alembic.config import Config

password = getpass.getpass("Senha local de postgres: ")
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://postgres:"
    + quote(password, safe="")
    + "@localhost:5432/identify_db"
)
config = Config("alembic.ini")
command.current(config, verbose=True)
command.upgrade(config, "head")
command.current(config, verbose=True)
'@ | .\.venv\Scripts\python.exe -
```

Feche esse processo ao terminar; a API deve voltar a usar exclusivamente `identify_user`. Confira `alembic current -v` e `alembic heads` com a configuração de runtime.

## 3. Configuração e inicialização

Copie `2identify_api\.env.example`, `2identify_admin\.env.example` e `2identify_operador\.env.example` para os respectivos `.env` ignorados pelo Git. Configure a URL local da API para `identify_user@localhost:5432/identify_db` com senha corretamente codificada na URL. Gere valores aleatórios distintos, com pelo menos 32 caracteres, para `AUTH_TOKEN_SECRET`, `OPERATOR_CATALOG_TOKEN` e `SAFETY_DEVICE_TOKEN`; o token de catálogo deve coincidir entre API e Operator, e o token da torre entre API e firmware. Não use os placeholders dos exemplos.

O Admin usa `API_URL`; não precisa acessar o banco diretamente. O Operator usa `API_URL` e `OPERATOR_CATALOG_TOKEN`. Configure `PPE_MODEL_PATH` e confira o hash do checkpoint. Para cada câmera cadastrada pelo Admin, configure no `.env` local do Operator `CAMERA_SOURCE_<id>` quando a fonte exigir credenciais ou quando for USB. RTSP privado e parâmetros de stream ficam somente nesse arquivo ignorado. Para USB, sonde o índice **nesta** estação com `scripts\probe_usb_cameras.py`; o índice do PC anterior não é portátil. Consulte [o guia de campo](metaindustria-multicamera-field-guide.md) para vincular IDs reais após o cadastro e conferir setor/operação.

Em terminais separados:

```powershell
# Em 2identify_api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws-max-size 65536
Invoke-RestMethod http://127.0.0.1:8000/health

# Em 2identify_admin
.\.venv\Scripts\python.exe main.py

# Em 2identify_operador
.\.venv\Scripts\python.exe main.py --check
.\.venv\Scripts\python.exe main.py
```

Para o celular e a torre alcançarem a API na LAN, use `--host 0.0.0.0` somente em uma rede confiável e configure o endereço do PC nos clientes. Mantenha **um worker** da API, pois o registro de segurança em tempo real é em memória. Na pasta `2identify_web`, `py -3.12 -m http.server 5173 --bind 0.0.0.0` serve o frontend estático. Verifique o acesso pelo celular na mesma rede; o frontend usa a API do host na porta 8000.

## 4. Supabase e ESP32

Supabase não substitui `identify_db`. Se houver acesso cloud autorizado, em `2identify_api` configure `.env.mobile` com `.\.venv\Scripts\python.exe -m scripts.configure_mobile_poc` (entrada oculta). Execute primeiro `.\.venv\Scripts\python.exe -m scripts.prepare_mobile_poc_supabase --preflight-only` e revise o resultado. O bootstrap cloud aprovado vai somente até `e4a7b8c9d0e1`; não faça `alembic upgrade head` no Supabase. Só depois do preflight seguro use `--apply` e `.\.venv\Scripts\python.exe -m scripts.sync_mobile_poc_to_supabase`, inicialmente sem `--apply`. Para usar a API contra a cloud em uma PoC isolada, pare a API local e execute `.\.venv\Scripts\python.exe -m scripts.run_mobile_poc_api`; o frontend continua passando pela API. Sem `CLOUD_DATABASE_URL` real, a validação cloud permanece pendente.

O firmware está em `2identify_operador\firmware\esp32_safety_signal`. Copie `device_config.example.h` para `device_config.h` local e configure Wi-Fi, endereço/porta da API e o token do dispositivo sem versioná-los. Confira [o README do firmware](../2identify_operador/firmware/esp32_safety_signal/README.md) antes do teste físico. Não é necessário mudar GPIO, protocolo ou firmware para esta entrega.

## 5. Validação após a instalação

```powershell
# Cada diretório usa o próprio .venv
.\.venv\Scripts\python.exe -m pytest -q

# Em 2identify_web, com Node.js disponível
node --test
```

No Admin, cadastre as câmeras no setor escolhido, confirme a lista de câmeras ativas/inativas e a associação da operação. No Operator, selecione somente o subconjunto desejado; confira um tile por câmera, imagem, status, isolamento de área de risco e alertas com `camera_id` correto. Os testes físicos de RTSP, USB, Pose/PPE, celular e ESP32 dependem da rede e do hardware da apresentação.
