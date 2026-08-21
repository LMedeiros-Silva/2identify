# Auditoria somente leitura do `identify_db`

Data da inspeção: 20 de agosto de 2026.

## Método e garantias

A inspeção foi executada com o SQLAlchemy Inspector dentro de uma transação PostgreSQL
marcada com `SET TRANSACTION READ ONLY`. Foram lidos apenas metadados de tabelas, colunas,
chaves, índices e a versão Alembic. Nenhum registro de negócio foi consultado e nenhum DDL,
`create_all`, migration, `stamp`, `INSERT`, `UPDATE` ou `DELETE` foi executado.

Schema analisado: `public`.

Versão registrada em `alembic_version`: `441c04c14c57`.

## Estrutura real encontrada

| Tabela | Colunas principais | Restrições confirmadas |
| --- | --- | --- |
| `usuarios` | `id`, `nome`, `username`, `senha_hash`, `perfil`, `ativo`, `criado_em`, `atualizado_em` | PK `id`; índice único `username` |
| `setores` | `id`, `nome`, `descricao`, `ativo`, `criado_em` | PK `id`; `nome` único |
| `epis` | `id`, `nome`, `codigo`, `descricao`, `ativo`, `criado_em` | PK `id`; `nome` e `codigo` únicos |
| `funcionarios` | `id`, `nome`, `matricula`, `cargo`, `turno`, `foto`, `ativo`, `setor_id`, `criado_em`, `atualizado_em` | PK `id`; `matricula` único; FK para `setores` com `RESTRICT` |
| `funcionario_epis` | `id`, `funcionario_id`, `epi_id`, `obrigatorio`, `entregue`, `criado_em` | PK `id`; FKs para `funcionarios` (`CASCADE`) e `epis` (`RESTRICT`) |
| `cameras` | `id`, `nome`, `descricao`, `endereco`, `setor_id`, `ativa`, `criado_em` | PK `id`; FK para `setores` com `RESTRICT` |
| `ocorrencias` | `id`, `funcionario_id`, `camera_id`, `tipo`, `descricao`, `confianca`, `imagem`, `video`, `detectado_em` | PK `id`; FKs opcionais para `funcionarios` e `cameras`, ambas com `SET NULL` |
| `alertas` | `id`, `ocorrencia_id`, `nivel`, `status`, `observacao`, `criado_em`, `recebido_em`, `encerrado_em`, `encerrado_por` | PK `id`; ocorrência única com `CASCADE`; usuário de encerramento opcional com `SET NULL` |

Além dessas oito tabelas de domínio, existe a tabela técnica `alembic_version`. Todas as
colunas temporais inspecionadas estão configuradas com timezone. Apenas os identificadores
autoincrementais possuem defaults de servidor; os demais defaults descritos pelos modelos do
Admin são aplicados no lado Python.

## Comparação com o Admin

Os nomes de tabelas e colunas, tipos, nulabilidade, PKs, FKs, ações `ON DELETE`, índices
únicos e a revisão final estão alinhados com os models e a cadeia de quatro migrations do
Admin. As relações ORM são comportamento Python e, portanto, não aparecem como objetos
separados no PostgreSQL.

Pontos importantes que não devem ser corrigidos automaticamente:

- `funcionario_epis` não possui unicidade composta para `(funcionario_id, epi_id)`;
- `ocorrencias.confianca` não possui `CHECK` limitando o valor;
- campos textuais como `perfil`, `tipo`, `nivel` e `status` não possuem enum ou `CHECK`;
- os defaults de negócio são majoritariamente client-side, não `server_default`;
- a revisão intermediária `d5338781e8f0` remove campos temporais e a revisão final os
  readiciona; reproduzir essa sequência sobre dados existentes exige análise e backfill.

O banco atual já está na revisão final. Por isso nenhuma dessas migrations foi executada.

## Conceitos futuros do Operador — análise sem criar tabelas

| Conceito | Reuso possível | Necessidade provável, sujeita à aprovação |
| --- | --- | --- |
| `Operation` | pode referenciar `setores`, `cameras` e `epis` | tabela `operations` |
| `RequiredPPE` | reutiliza `epis`; `funcionario_epis` representa obrigação por funcionário, não por operação | associação `operation_required_epis` |
| `OperatorSession` | autenticação pode usar `usuarios`; sessão JWT pode ser stateless | vínculo explícito usuário–funcionário e, somente se houver revogação/auditoria, tabela de sessões |
| `WorkSession` | referencia funcionário, operação e câmera existentes | tabela `work_sessions` |
| `Manual` | arquivo deve ficar em storage e o banco guardar metadados/referência | tabela `manuals`, se manuais forem gerenciáveis |
| `RiskArea` | referencia câmera/setor | tabela `risk_areas` para configuração/geometry versionada |
| `FaceIdentity` | `funcionarios.foto` guarda apenas um caminho e não substitui template biométrico | tabela protegida de identidades/templates faciais |

Uma eventual evolução de alertas deve reutilizar `ocorrencias` e `alertas`, adicionando apenas
os relacionamentos e campos que forem aprovados após o contrato HTTP da etapa 34.
