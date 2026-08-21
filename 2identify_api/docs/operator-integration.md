# Etapa 34 — comunicação Operator → API

## Escopo implementado

O login alternativo por credenciais é o primeiro fluxo real do Operador centralizado na API:

```text
CredentialLoginWorker (QThread)
        ↓
OperatorApiClient
        ↓ POST /auth/login
2Identify API
        ↓ SELECT somente leitura
usuarios / PostgreSQL
        ↓ bcrypt + JWT
OperatorSessionContext (memória)
```

O Operador já possuía cliente, serviço, worker e controller compatíveis. Nenhum acesso direto
ao PostgreSQL foi introduzido e nenhuma mudança de UI foi necessária.

## Contrato

Requisição:

```json
{
  "username": "operador.15",
  "password": "senha"
}
```

Resposta HTTP 200:

```json
{
  "access_token": "<token-assinado>",
  "token_type": "bearer",
  "expires_in": 1800,
  "operator": {
    "id": 15,
    "name": "João Silva",
    "profile": "operador",
    "profile_photo_reference": null
  }
}
```

O cliente ignora com segurança os campos adicionais `expires_in` e `profile`, mantendo
compatibilidade com o contrato já testado. O token permanece somente na sessão em memória e
é removido no logout.

## Política provisória de identidade

- `operator.id` representa `usuarios.id`, não `funcionarios.id`;
- `profile_photo_reference` é `null`, pois `usuarios` não possui foto;
- os perfis permitidos são configurados por `AUTH_ALLOWED_PROFILES`;
- o padrão permite somente `operador`;
- `administrador` exige opt-in em `AUTH_ALLOWED_PROFILES` depois da rotação das credenciais de
  seed, caso o acesso emergencial seja realmente necessário;
- nenhum vínculo entre conta, funcionário e identidade facial é inferido por nome ou ID.

## Comportamento de falha

- `401`: usuário/senha, senha acima de 72 bytes, conta inativa ou perfil rejeitado; nenhuma
  sessão é criada;
- `422`: payload estruturalmente inválido, sem refletir os valores recebidos;
- `503`: banco indisponível; resposta sanitizada;
- timeout/rede no desktop: erro recuperável e nova tentativa manual;
- uma oscilação posterior da API não encerra uma operação local já em andamento.

Não há retry automático do `POST`, evitando autenticações concorrentes ou comportamento
surpreendente. CORS não é necessário para o cliente desktop. Antes de expor a porta fora de
`localhost`, adicione rate limiting compartilhado no proxy/Redis.

## Deliberadamente adiado

- `POST /auth/face`: exige persistência biométrica e vínculo de identidade;
- operações/EPIs/áreas/manuais remotos: exigem tabelas e contratos ainda não aprovados;
- refresh token, revogação e bloqueio persistente: exigem política e possivelmente schema;
- WorkSession, ocorrências e alertas remotos: dependem de identidade e operação persistidas;
- HTTPS/certificados: obrigatório no deployment fora da mesma máquina.
