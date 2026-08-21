# Estratégia de baseline do Alembic

O banco existente foi criado pelo projeto Admin e já possui uma tabela
`alembic_version`. Para manter uma única linha histórica, as quatro revisões do Admin são
copiadas sem alterações para esta pasta.

Na etapa 33:

- nenhuma revisão nova é criada;
- `upgrade`, `downgrade` e `stamp` não são executados;
- o `autogenerate` permanece bloqueado, pois a API ainda não possui metadados completos;
- a versão registrada no banco é apenas lida pelo inspetor de esquema.

Antes da primeira migração futura, será obrigatório reconciliar todos os modelos da API com
o esquema real e revisar a migração proposta manualmente. Isso evita uma segunda linhagem e
impede que tabelas pertencentes ao Admin sejam interpretadas como objetos a remover.
