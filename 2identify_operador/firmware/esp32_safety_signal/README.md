# Torre de sinalização ESP32 — relés ACTIVE LOW

Integração com o estado agregado dos alertas persistidos da `2identify_api`.
Não acessa PostgreSQL, Operator diretamente nem MQTT. O GPIO 13 está reservado,
sem controle local do estado. A torre é sinalização auxiliar, não um intertravamento
de segurança certificado.

## Contrato elétrico

| Saída | GPIO | GREEN | YELLOW | RED | DISCONNECTED |
|---|---:|---|---|---|---|
| Verde | 26 | ligado | desligado | desligado | desligado |
| Amarelo | 33 | desligado | ligado | desligado | pisca 1000 ms |
| Vermelho | 21 | desligado | desligado | pisca 500 ms | desligado |
| Buzina (relé) | 23 | desligada | desligada | acompanha vermelho | desligada |

LOW liga, HIGH desliga. Não usa `tone()`; a buzina tem alimentação controlada
pelo relé. Não usa mais pares de LEDs ou saídas brancas. Verifique compatibilidade
3,3 V das entradas e o circuito de potência com profissional habilitado; cargas
não devem ser alimentadas pelos GPIOs. A inicialização em software não garante
o estado elétrico durante reset/boot: confira resistores de pull-up e módulo
de relés antes de conectar as cargas.

## Dependências exatas para Arduino IDE

- Gerenciador de placas: **esp32**, autor **Espressif Systems** — compilado com **3.3.11**.
- Gerenciador de bibliotecas: **WebSockets**, autor **Markus Sattler** (Links2004) — **2.7.2**.
- **ArduinoJson**, autor **Benoit Blanchon** — **7.4.2**.
- `Arduino.h` e `WiFi.h` acompanham o core ESP32.

Referências oficiais:
[ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html),
[WebSockets](https://github.com/Links2004/arduinoWebSockets),
[ArduinoJson](https://arduinojson.org/v7/api/json/deserializejson/).

Opcional, com Arduino CLI instalado:

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.11 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install "WebSockets@2.7.2" "ArduinoJson@7.4.2"
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/esp32_safety_signal
```

O alvo testado é ESP32 Dev Module (ESP32 clássico). Selecione sua placa e porta
USB reais no Arduino IDE antes de enviar.

## Configurar API e token

Na pasta `2identify_api`, com o ambiente virtual ativo:

```powershell
python -m pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie o valor gerado **somente** para o arquivo local `2identify_api/.env`:

```dotenv
SAFETY_DEVICE_TOKEN=COLE_O_TOKEN_GERADO
```

Não altere `JWT_SECRET` para usar o token da torre. A variável
`SAFETY_DEVICE_TOKEN` já existe no `.env.example`; não exige nova migration.

Após configurar o banco e remover credenciais previsíveis, inicie para um teste
em **rede privada confiável** (um processo, sem balanceamento entre workers):

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

O firmware usa WebSocket sem TLS (`ws://`), portanto não publique esta porta na
Internet. Fora de uma rede isolada, é necessário WSS/HTTPS com certificado validado
e a correspondente configuração TLS no firmware. Nunca desabilite validação de
certificado. Não foi criada regra de firewall automaticamente.

## Descobrir IP e configurar ESP32

1. No PC da FastAPI, execute `ipconfig`.
2. Copie o **Endereço IPv4** do adaptador Wi-Fi/Ethernet conectado à mesma rede
   do ESP32. Não use IP de VPN, adaptador virtual, gateway, `0.0.0.0` ou `127.0.0.1`.
3. Abra `esp32_safety_signal.ino` no Arduino IDE.
4. Para copiar/colar isoladamente, edite no início:
   - `WIFI_SSID`: nome exato da rede Wi-Fi compatível com sua placa;
   - `WIFI_PASSWORD`: senha dessa rede;
   - `API_HOST`: IPv4 do passo 2, sem `http://`, porta ou caminho;
   - `API_PORT`: 8000;
   - `API_PATH`: mantenha `/ws/devices/safety`;
   - `DEVICE_TOKEN`: exatamente o valor de `SAFETY_DEVICE_TOKEN`.
5. **No repositório**, prefira copiar `device_config.example.h` para
   `device_config.h` e editar só essa cópia ignorada pelo Git. Se ela existir,
   suas definições têm prioridade sobre os placeholders do .ino.
6. Não versione senhas ou token real no .ino. Nunca remova a proteção de
   `device_config.h`/ `.env` no Git.
7. Se necessário, autorize TCP 8000 no Firewall somente para a rede privada
   do teste e verifique se o roteador não isola clientes Wi-Fi.
8. Compile, selecione a porta e faça upload. Abra o Monitor Serial em **115200 baud**.

## Comunicação e estado

Endpoint reutilizado: `ws://API_HOST:8000/ws/devices/safety`.
Autenticação: `Authorization: Bearer <DEVICE_TOKEN>`, somente no handshake.
Token ausente/incorreto recebe HTTP 401. Token não configurado ou falha ao ler o
estado inicial recebe 503. Não são permitidos token em URL ou comandos de cliente.

Mensagem existente preservada (não inclui dados pessoais):

```json
{
  "type": "safety_state",
  "schema_version": 1,
  "state": "RED",
  "reason": "PERSON_IN_RISK_AREA",
  "active_conditions": 2,
  "updated_at": "2026-09-03T00:00:00Z"
}
```

`reason` é `null` em GREEN. Nos demais estados usa os motivos já mapeados da API.
O ESP32 valida tipo, versão e estado, mas **não calcula criticidade**.

A API lê todos os alertas não encerrados; `critical/critico` prevalece sobre
`warning/aviso`. Sem alertas => GREEN; só avisos => YELLOW; qualquer crítico => RED.
Categorias desconhecidas permanecem relevantes; níveis não críticos seguem o
mapeamento de atenção existente do Admin, não são tratados como ausência de alerta.

- Recalcula após criação, escalada, resolução do Operator e ações do Admin.
- Resolução usa o mesmo UUID e `status=resolved` com `resolved_at`, encerrando
  o registro existente. Não cria tabela ou motor de detecção novo.
- Confirmar (`lido`) **continua ativo**; encerrar (`encerrado`) deixa de contar.
- Parar a operação ou fechar o software **não comprova resolução do risco**:
  os alertas pendentes continuam ativos até resolução recebida ou encerramento no Admin.
- O envio final tenta descarregar transições já observadas antes do logout.
  Não existe outbox durável: indisponibilidade prolongada/crash pode exigir
  conferência e encerramento manual no Admin.
- Uma repetição antiga não reabre um alerta encerrado nem rebaixa sua severidade.
- Conectar/reconectar lê o banco e envia o estado atual, mesmo após reiniciar a API.
- Alterações no banco feitas fora da API não emitem eventos automaticamente.

O broker envia mudanças imediatamente e repete o último `safety_state` validado
a cada **no máximo 10 s** como heartbeat de aplicação; isso não consulta o banco
por polling. Ping/pong do WebSocket verifica também o transporte.
Sem mensagem válida da aplicação por **30 s**, JSON inválido ou perda de conexão,
o ESP entra em DISCONNECTED. PONG sozinho não renova um GREEN antigo.
Uma falha de recálculo invalida o cache: o canal fecha no próximo heartbeat;
a persistência/publicação do alerta ao Admin não é descartada.

## Teste integrado completo

Use uma operação/câmera de teste, sem exposição real a risco industrial.
Entre no Operator **com usuário e senha da API**. Face ID local com token somente
de catálogo não autoriza publicação de alertas; esse fluxo não foi alterado.

1. **Sem alertas ativos**: encerre apenas as ocorrências de teste existentes pelo Admin,
   inicie API e ESP. Boot amarelo piscando; após snapshot GREEN, verde contínuo.
2. **Aviso**: inicie monitoramento; simule uma ausência de EPI configurado ou uma
   condição que o AlertEngine classifique como warning. Após debounce e entrega,
   confira alerta no Admin e amarelo contínuo.
3. **Crítico**: mantenha a condição até a escalada configurada ou produza um evento
   crítico de teste. Confira vermelho + relé da buzina alternando juntos a cada 500 ms.
4. **Resolução e prioridade**: mantenha um warning independente enquanto resolve o
   crítico. Após a resolução validada pelo detector, espere YELLOW; resolva os demais
   e espere GREEN. Se fechar pelo Admin, confirme antes de encerrar; confirmação
   sozinha não deve desligar a sinalização.
5. **API fora**: pare a API com Ctrl+C. ESP deve mostrar amarelo piscando, sem verde,
   vermelho ou buzina; o watchdog de mensagens limita a detecção de conexão travada
   a 30 s (sujeito aos tempos do transporte).
6. **Reconexão**: religue a API. ESP reconecta e recebe o estado persistido. Repita
   reiniciando o ESP com um crítico ainda ativo: deve receber RED sem novo evento.
7. **Wi-Fi fora**: desconecte a rede do teste; confira DISCONNECTED e recuperação
   automática após retorno. GPIO 13 não deve alterar a torre.
8. **Token inválido**: use temporariamente um token de teste incorreto apenas no ESP;
   a conexão deve ser recusada e o verde não deve acender. Restaure o token depois.

## Verificação automatizada

Na API: `python -m pytest -q -p no:cacheprovider`.
No Operator: `python -m pytest -q -p no:cacheprovider`
(use `QT_QPA_PLATFORM=offscreen` em testes Qt sem interface).

Testes cobrem prioridade, alterações persistidas, reconexão, autenticação,
heartbeat, falha do banco, isolamento de operador, resolução/escala combinadas,
idempotência, proteção do Admin quando a torre falha e descarregamento no logout.
O teste Python do firmware verifica seu contrato estático; não simula circuitos.
A compilação Arduino é adicional. Testes físicos de relés, buzina, alimentação e
rede devem ser realizados na bancada antes do uso.
