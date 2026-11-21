# AGENTS.md (raiz)

PWA para ler mangás (CBZ/CBR/pasta), livros (EPUB) e PDF, instalável no iOS. Conteúdo no servidor; o app consome a API.
Stack: Python/FastAPI (backend) + React/TypeScript/Vite (frontend). Detalhes e roteiro: `docs/PLANO.md`.

**Como usar:** leia este arquivo e, em seguida, **apenas** o `AGENTS.md` do módulo em que vai trabalhar. Não leia os demais.

## Regras gerais (valem em todo o projeto)

1. **Idioma:** documentação em pt-BR; código, nomes e commits em inglês (Conventional Commits).
2. **Arquitetura:** backend em Hexagonal (Ports & Adapters) leve; frontend por feature. Dependências só apontam para dentro (regra detalhada em cada módulo). Não desative o teste de arquitetura: corrija o código.
3. **Segurança (somente dentro do app):** o app é público na web e deve se defender sozinho; não tratar rede/VPN/servidor. Proteções obrigatórias: anti brute force no login, CSRF, rate limit, cabeçalhos de segurança (detalhes em `backend/AGENTS.md`). Toda entrada do cliente é hostil; nenhum caminho de arquivo vem do cliente; toda consulta de dados de usuário filtra por `user_id`; sem segredos no repositório; sem `eval`, `shell=True` ou SQL por concatenação.
4. **Testes:** `scripts/check` deve ficar verde. Bug ou finding corrigido exige teste `test_reg_<NNN>_<slug>` em `tests/regression/`. Nunca remover, enfraquecer ou pular teste para passar. Se não rodou, diga que não rodou.
5. **Mudança pequena e focada.** Uma preocupação por entrega. Em dúvida real, pergunte.
6. **Documentação viva:** mudou código ⇒ atualize o mapa e o changelog na mesma entrega (regras em `docs/AGENTS.md`).
7. **Proibido sem autorização do dono:** apagar dados/migrações, desligar verificações de segurança ou CI, adicionar telemetria/serviços externos, fazer deploy, raspar fontes de terceiros, alterar ADR aceito. **Exceção autorizada pelo dono em 2026-11-20 (ADR 0015):** consulta de capa e descrição em fontes públicas de metadados, só pelo `SafeGateway`, com lista fixa de hosts, enviando apenas o título limpo e a sinopse pública. `METADATA_ENABLED=false` desliga tudo. **Ampliação de 2026-11-21 (ADR 0018, Proposto):** o 8º host da lista, `api.github.com`, entrou para a checagem de release (`releases/latest` do repositório configurado). Essa ampliação foi informada pelo coordenador da entrega; a confirmação direta do dono ainda está pendente. O webhook de atualização é a única saída fora do `SafeGateway`, com destino só por configuração e assinatura. Nenhuma outra integração externa está coberta.

## Mapa do projeto

| Módulo | O que faz | Regras do módulo |
|---|---|---|
| `backend/` | API REST (`/api/v1`): auth, biblioteca, páginas/arquivos, progresso de leitura, preferências | `backend/AGENTS.md` |
| `backend/app/domain/` | Entidades e regras puras (Item, Progress, Locator). Sem framework | `backend/AGENTS.md` |
| `backend/app/services/` | Casos de uso (escanear biblioteca, salvar progresso, obter página) | `backend/AGENTS.md` |
| `backend/app/ports/` | Interfaces (repositório, storage, extrator de formato, fonte externa) | `backend/AGENTS.md` |
| `backend/app/adapters/` | Implementações: banco, disco, leitores CBZ, pasta e EPUB (CBR e PDF pendentes), saída de rede. **Área mais sensível a segurança** | `backend/app/adapters/AGENTS.md` |
| `backend/app/api/` | Routers, schemas HTTP, autenticação (camada fina) | `backend/AGENTS.md` |
| `backend/tests/` | unit, integration, regression, security, architecture | `backend/AGENTS.md` |
| `frontend/` | PWA: telas, leitores (mangá e EPUB; PDF pendente), progresso, aviso de versão, tema claro/escuro, offline | `frontend/AGENTS.md` |
| `docs/` | Plano, mapas, ADRs (`docs/adr/README.md`), histórico | `docs/AGENTS.md` |
| `docs/security/` | Protocolo de auditoria, findings, fila de remediação | `docs/security/AGENTS.md` |
| `infra/` | Dockerfile/compose do app e receptor de referência do webhook (`infra/deploy-hook/`). Rede, VPN e TLS são do servidor, fora de escopo | `infra/AGENTS.md` |
| `.github/` | CI, release por tag, dependabot e scripts de notas de release | `infra/AGENTS.md` |
| `scripts/` | `check` (lint, tipos, testes, SAST, auditoria de dependências) | `scripts/README.md` |
| `SECURITY.md` | Como reportar vulnerabilidade (canal privado) | — |

Para localizar arquivo por arquivo: `docs/maps/CODEMAP.md`.
