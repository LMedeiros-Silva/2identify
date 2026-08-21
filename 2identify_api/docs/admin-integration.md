# Contrato HTTP do Admin — Etapa 35

Esta etapa adiciona leitura administrativa à API sem migrations, DDL ou escrita em tabelas de
negócio. A autenticação usa a tabela `usuarios`; o dashboard agrega somente
`funcionarios`, `funcionario_epis` e `alertas`.

## Autenticação

`POST /auth/admin/login`

```json
{
  "username": "admin",
  "password": "senha-local"
}
```

Resposta HTTP 200:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 1800,
  "administrator": {
    "id": 1,
    "name": "Administrador",
    "username": "admin",
    "profile": "administrador"
  }
}
```

Somente contas ativas cujo perfil normalizado seja exatamente `administrador` são aceitas. O
JWT usa algoritmo fixo HS256, issuer configurado e audience exclusiva `2identify-admin`. O
login legado do Operador permanece em `POST /auth/login`, aceita apenas `operador` e continua
usando `2identify-operator`.

## Recursos protegidos

`GET /admin/me` retorna diretamente o objeto de identidade do exemplo acima. Antes de
responder, a API valida assinatura, issuer, audience e claims obrigatórias, extrai `sub` e
reconsulta `usuarios` para confirmar que a conta continua ativa e administrativa.

`GET /admin/dashboard/summary` retorna:

```json
{
  "active_employees": 12,
  "ppe_assignments": 30,
  "delivered_ppe": 24,
  "ppe_delivery_percentage": 80.0,
  "alerts": 5,
  "critical_alerts": 2,
  "generated_at": "2026-08-20T12:00:00Z"
}
```

O percentual é arredondado para uma casa decimal e vale `0.0` quando não há atribuições. Ele
mede somente entrega de EPI, não conformidade, uso correto ou segurança do ambiente.

## Erros e cache

- 401 para credenciais, bearer, audience, perfil ou conta ativa inválidos;
- 422 para JSON incompatível, sem refletir senha nem o conteúdo recebido;
- 503 sanitizado quando o PostgreSQL está indisponível.

Respostas de autenticação e recursos administrativos incluem `Cache-Control: no-store` e
`Pragma: no-cache`. Nenhum endpoint desta etapa executa `INSERT`, `UPDATE` ou `DELETE`.

## Implantação segura

O projeto já teve uma credencial previsível em seed histórico. Não altere o banco por esta API:
rotacione essa senha pelo fluxo administrativo autorizado antes de expor o serviço. Use segredo
JWT forte e exclusivo por ambiente, HTTPS e limitação de tentativas no proxy. Para teste local,
mantenha o Uvicorn ligado somente a `127.0.0.1`.
