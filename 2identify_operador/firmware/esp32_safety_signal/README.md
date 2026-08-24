# Sinalizador de segurança ESP32

Firmware comandado exclusivamente pelo estado global publicado pela `2identify_api`.
O botão do GPIO 13 é configurado como entrada, mas não altera o modo normal.

## Dependências Arduino

- placa `esp32` da Espressif Systems;
- biblioteca `arduinoWebSockets` de Markus Sattler;
- biblioteca `ArduinoJson` de Benoit Blanchon, versão 7.

## Configuração

Crie a configuração local ignorada pelo Git e edite somente essa cópia:

```powershell
Copy-Item device_config.example.h device_config.h
```

Em `device_config.h`, configure:

- `WIFI_SSID` e `WIFI_PASSWORD`;
- `API_HOST`: IPv4 da máquina que executa a API na mesma rede, nunca `127.0.0.1`;
- `API_PORT`: por padrão `8000`;
- `DEVICE_TOKEN`: exatamente o mesmo valor de `SAFETY_DEVICE_TOKEN` no `.env` da API.

O token deve ter pelo menos 32 caracteres aleatórios. `device_config.h` está no
`.gitignore`; não remova essa proteção nem versione Wi-Fi, token ou outro segredo real.

Inicie a API acessível pela rede local:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No Windows, execute `ipconfig`, encontre o `Endereço IPv4` do adaptador Wi-Fi/Ethernet
ativo e use esse valor em `API_HOST`. Autorize a porta TCP 8000 no Firewall apenas para
a rede privada usada no teste.

## Estados físicos

- conectado e seguro: brancos fixos + verdes fixos;
- condição `medium`: brancos fixos + amarelos fixos;
- condição `critical`: brancos fixos + vermelhos e buzzer de 1000 Hz a cada 500 ms;
- Wi-Fi/API/WebSocket indisponível: brancos fixos + amarelos piscando lentamente, sem buzzer.

O endpoint é `ws://API_HOST:API_PORT/ws/devices/safety` e exige o cabeçalho
`Authorization: Bearer <DEVICE_TOKEN>`. Ao conectar ou reconectar, a API envia o estado
atual imediatamente.
