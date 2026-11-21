# ADR 0007: Usuários por username, SQLite em WAL, Argon2id e composição única

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- `docs/PLANO.md` §4 previa `User` com `email`.
- ADR 0002 proíbe cadastro público e serviço externo de e-mail sem autorização do dono. Só o dono cria contas.
- `docs/PLANO.md` §7 prevê SQLite em WAL com SQLAlchemy e Alembic, com troca futura para outro banco.
- ADR 0002 exige Argon2id e política mínima de senha.
- ADR 0001 prevê um ponto de composição ports → adapters na Fase 1.

## Decisão

| Tema | Decisão |
|---|---|
| Identificador da conta | `username`: 3–64 caracteres, `[a-z0-9._-]`, começa com letra ou dígito, normalizado em minúsculas, único sem distinção de caixa no banco. Sem e-mail |
| Criação de conta | Só pelo CLI admin (`python -m app.cli create-user`). Sem rota pública de cadastro |
| Banco | SQLite com `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON` e `busy_timeout=5000` em toda conexão |
| Esquema | Alembic. Revisão `0001` cria `users`, `refresh_tokens`, `login_attempts` e `audit_log` |
| Senha | Argon2id com t=3, m=64 MiB, p=4. Usuário inexistente gasta o mesmo trabalho, com hash dummy |
| Montagem | `backend/app/composition.py` é o único ponto de montagem ports → adapters. `api/deps.py` e `cli.py` só o usam |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| E-mail como identificador | Exige contato e, para recuperação, serviço externo de e-mail, proibido sem autorização (ADR 0002). Sem cadastro público, não há necessidade |
| PostgreSQL já na Fase 1 | Uso individual não exige; PLANO §7 prevê migração depois, com SQLAlchemy |
| `synchronous=FULL` | Mais durável e mais lento. Não adotado nesta decisão; ver consequências |

## Consequências

- Positivas: menos dado pessoal armazenado; contas sem fluxo de cadastro; banco simples de operar; leitores não bloqueiam o escritor em WAL; o teste de arquitetura impede CLI e API de contornar a composição.
- Negativas:
  - Com `synchronous=NORMAL`, uma queda de energia pode desfazer as últimas transações confirmadas. O banco não corrompe.
  - Se um dia houver recuperação de senha por contato, será preciso novo ADR para incluir e-mail.
  - Migrar para outro banco exige revisar os pragmas e o tipo `UTCDateTime`.
- Obrigações: não alterar este ADR. Mudar o identificador ou o modo de durabilidade exige novo ADR que substitua este. Toda mudança de esquema vai por nova revisão Alembic.

Complementa ADR 0001 (ponto de composição) e ADR 0002 (cadastro e senhas). Não altera ADR 0001 a 0006.
