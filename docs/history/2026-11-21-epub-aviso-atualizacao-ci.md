# 2026-11-21 — Leitor de EPUB, aviso e atualização por release, CI e release

Esta entrada documenta o que foi entregue no código desde `2026-11-21-series-e-metadados.md` e a atualização dos mapas e da documentação nesta rodada. Esta entrada não altera código. Números de testes: os do `scripts/check` e do CI não foram reexecutados aqui; as contagens por arquivo foram lidas do disco (`def test`, `it(`/`test(`).

## O que foi feito

| Área | Entrega | Onde |
|---|---|---|
| Leitura de EPUB | Metadados e sumário (`GET /items/{id}/book`), capítulo sanitizado (`/book/chapters/{n}`, com `theme` e `size`), imagens (`/book/res/{rid}`); DRM recusado; fontes e SVG nunca servidos | `backend/app/domain/book.py`, `ports/book_reader.py`, `services/book.py`, `api/books.py`, `api/book_schemas.py`, `adapters/extractors/epub.py`, `_epub_safe.py`, `_epub_html.py`, `_epub_css.py` |
| Preferências de livro | Migração `0008` (`book_font_scale` 80–200, padrão 100; `book_theme` auto, light, dark, sepia, padrão auto) | `backend/migrations/versions/0008_book_reader_preferences.py`, `api/progress_schemas.py` |
| Progresso de livro | `locator = capítulo * 10000 + offset_bp`; concluído no último capítulo com offset ≥ 9000 | `backend/app/domain/progress.py` |
| Contrato de séries | Capítulo traz `type` (manga, book, pdf); série traz `kind` (manga, book, mixed), derivado | `backend/app/api/series_schemas.py`, `backend/app/domain/series.py` (REG-027) |
| Leitor EPUB (frontend) | `/ler/:itemId` escolhe o leitor pelo tipo (`app/ReaderRoute.tsx`); capítulo em `iframe sandbox="allow-same-origin"`; índice, ajustes de fonte e tema | `frontend/src/features/reader-epub/**`, `frontend/src/app/ReaderRoute.tsx`, `shared/items/useItem.ts`, `shared/series/useReaderNav.ts` (movido de `reader-manga`) |
| Aviso de release | `GET /api/v1/system/version` (usuário comum recebe só `current` e `update_available`); admin: detalhe, `POST /system/update/check` (3/min) e `POST /system/update` (202, 409, 502, 503) | `backend/app/api/system.py`, `domain/release.py`, `services/update_service.py`, `adapters/http/safe_gateway.py` (`api.github.com`) |
| Atualização pelo app | Webhook assinado (HMAC-SHA256) para o receptor no host; única saída fora do `SafeGateway`; destino só por configuração; http só em rede do operador; app nunca acessa o Docker | `backend/app/adapters/http/webhook_notifier.py`, `ports/update_notifier.py`, `core/config.py` (`APP_VERSION`, `UPDATE_*`), `infra/deploy-hook/` |
| Frontend da atualização | Aviso só para admin (texto puro, link https); verificação manual e versão em Ajustes; polling limitado | `frontend/src/shared/system/**`, `app/AppUpdatePrompt.tsx`, `features/settings/hooks/useCheckUpdates.ts` |
| Service worker | `registerType: 'prompt'`; nada recarrega sozinho; "Recarregar" faz flush do progresso antes | `frontend/vite.config.ts`, `app/registerServiceWorker.ts`, `app/useAppUpdate.ts`, `shared/pwa/`, `shared/progress/flush-registry.ts` |
| CI e release | `ci.yml` (push em `master`, PR; backend, frontend, infra, gitleaks, build sem push); `release.yml` (tag `vX.Y.Z`: prepare, verify, publish no GHCR com proveniência e SBOM, release); dependabot; script de notas | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/dependabot.yml`, `.github/scripts/release_notes.py` |
| Imagem | `ARG APP_VERSION` no Dockerfile; compose com `APP_TAG` e `UPDATE_*` | `infra/Dockerfile`, `infra/compose.example.yml`, `.env.example` |
| Segurança | `SECURITY.md` na raiz (reporte privado pelo GitHub) | `SECURITY.md` |
| Decisões | ADR `0017` (CSP e iframe do capítulo EPUB) e `0018` (oitavo host e webhook); ambos **Proposto** | `docs/adr/0017-*.md`, `docs/adr/0018-*.md`, `docs/adr/README.md` (índice, novo) |
| Testes | `test_reg_024` a `test_reg_027`; suítes de EPUB, livros, atualização, webhook, release no `SafeGateway`, `kind`; frontend `epub-locator`, `reader-epub`, `series-books`, `system-update`, `pwa-update`; receptor e notas no CI | `backend/tests/**`, `frontend/tests/unit/**`, `infra/deploy-hook/test_receiver.py`, `.github/scripts/test_release_notes.py` |
| Docs | Mapas (`CODEMAP`, `API`, `SECURITY_MAP`, `TEST_MAP`, `ROUTES`, `ARCHITECTURE`, `DATAMODEL`); AGENTS (raiz, backend, adapters, tests, frontend, infra); `scripts/README.md`; `README.md`; `PLANO.md` (status); `CHANGELOG.md`; `docs/DEPLOY.md` (atualização reescrita) | ver lista em `CHANGELOG.md` |

## Decisões e status

| Decisão | Status | Motivo |
|---|---|---|
| CSP própria para a rota do capítulo, iframe com `allow-same-origin` sem scripts (ADR 0017) | Proposto | Afrouxa ADR 0006 em um caminho; exige confirmação do dono |
| Oitavo host `api.github.com` e webhook como saída fora do `SafeGateway` (ADR 0018) | Proposto | Amplia a regra 7 de `AGENTS.md`; a autorização foi informada pelo coordenador, sem confirmação direta do dono |

## Discrepâncias encontradas entre código e mapas (corrigidas nesta rodada)

| Mapa | Discrepância | Situação |
|---|---|---|
| `CODEMAP.md` | `features/reader-manga/hooks/useReaderNav.ts` não existe mais (movido para `shared/series/useReaderNav.ts`) | Corrigido |
| `CODEMAP.md` | Service worker descrito como `autoUpdate` | Corrigido: `prompt` |
| `CODEMAP.md` | `isReadable` descrito como "só mangá" | Corrigido: mangá e livro |
| `CODEMAP.md` | `.dockerignore` citado sem fato no disco (não exclui `.github`) | Corrigido |
| `CODEMAP.md` e `docs/adr` | Não havia índice de ADRs como arquivo; a lista estava só no CODEMAP | Criado `docs/adr/README.md` |
| `DATAMODEL.md` | Eventos `system.update_requested` e `system.update_failed` não listados | Corrigido |
| `DATAMODEL.md` | Locator de EPUB descrito como CFI | Corrigido: capítulo × 10000 + offset |
| `DEPLOY.md` | Seção de atualização dizia que as variáveis `UPDATE_*` "não existem" | Corrigido |
| `DEPLOY.md`, `SECURITY_MAP.md`, `ARCHITECTURE.md`, `CODEMAP.md` | Allowlist descrita com 7 hosts | Corrigido para 8 |
| `backend/AGENTS.md` | "18 arquivos em ports/" | Corrigido para 20 (`book_reader`, `update_notifier`) |
| `backend/tests/AGENTS.md` | Próximo número livre `024` | Corrigido para `028` |
| `frontend/AGENTS.md` | Locator de EPUB como CFI; estrutura sem `system`, `pwa`, `reader-epub` | Corrigido |
| `infra/AGENTS.md` | "CI inexistente (`.github/` não existe)" | Corrigido |
| `TEST_MAP.md` | `test_reg_` "próximo livre 024"; EPUB "sem código, sem teste"; CI "não existe" | Corrigido |
| `TEST_MAP.md` | `infra/deploy-hook/test_receiver.py` e `.github/scripts/test_release_notes.py` fora do mapa | Incluídos (46 e 13 funções) |
| `API.md` | 429 de `/system/update/check` com texto diferente do genérico | Documentado: `Too many requests` |
| `PLANO.md` | EPUB "não iniciado"; CI "planejado e não existe" | Corrigido |
| Código × pedido da rodada | O resumo falava em `rid` opaco; o código usa índice numérico (dígitos, até 6) | Documentado como índice numérico (ADR 0017 e `API.md`) |
| Código × `ADR` | `docs/adr/` não tinha índice | Criado |

## Contagens (lidas do disco)

| Escopo | Resultado |
|---|---|
| Backend | 1120 funções `def test` em 95 arquivos (parametrizados não expandidos) |
| Frontend | 315 blocos `it`/`test`/`it.each` em 23 arquivos |
| Infra e CI | 46 + 13 funções (receptor e notas de release) |
| Regressões | `001` a `013`, `015` a `027`; `014` reservado; próximo livre `028` |
| Migrações | `0001` a `0008` |
| ADRs | `0001` a `0016` Aceitos; `0017` e `0018` Propostos |
| Histórico | 8 entradas em `docs/history/` (esta inclusive) |

## Validação

| Item | Resultado | Fonte |
|---|---|---|
| Arquivos citados nos mapas existem no disco | Conferido (listagem e leitura dos módulos alterados) | Esta rodada |
| Cabeçalhos de segurança do capítulo, cache e fontes | Conferido no código (`api/security_headers.py`, `adapters/extractors/epub.py`, `_epub_html.py`) | Esta rodada |
| Receptor e assinatura | Conferido no código (`infra/deploy-hook/receiver.py`, `webhook_notifier.py`); o teste importa o receptor real | Esta rodada |
| `scripts/check` completo | Não reexecutado nesta rodada (escopo: documentação) | Informado pelo coordenador |
| CI e release no GitHub | Não executados; o primeiro run é validação pendente | — |
| Imagem com `APP_VERSION` e compose com `APP_TAG` | Não construída nesta rodada | — |

## Não validado

| Item | Motivo |
|---|---|
| Leitura de EPUB real em navegador (layout, rolagem, fontes) | Sem livro de teste no repositório |
| Service worker instalado e aviso de versão em aparelho real | Sem navegador ou iOS nesta rodada |
| Webhook contra o receptor em execução com Docker | Testado só com o receptor importado e runner falso |
| Consulta real a `api.github.com` com cota | Testes usam gateway falso |
| Confirmação do dono para o oitavo host e para CSP do capítulo | ADR 0017 e 0018 em Proposto |

## Pendências

| Item | Próximo passo |
|---|---|
| Aceite dos ADRs 0017 e 0018 | Dono confirma (ou pede ajuste) e o status vira Aceito |
| Primeira execução do CI e do release | Rodar em `master` e em uma tag `-rc` antes da primeira release final |
| Receptor de atualização em produção | Configurar `UPDATE_HOOK_*` no host, `UPDATE_WEBHOOK_*` no `.env` e testar com uma tag de teste |
| Backup de `covers/` e de `/data` | Decisão do dono (ver `docs/DEPLOY.md` §6) |
| PDF e CBR | Fase 4 (sem código) |
| FIND-2026-009 (`open`), M8 (hashes), reverificação de FIND-002 | Ver `docs/maps/SECURITY_MAP.md` |
