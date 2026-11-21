# 2026-11-21 — Séries e metadados de fontes públicas

Esta entrada documenta o que foi entregue no código (backend, frontend, migrações e infra) desde o MVP (`2026-11-20-mvp-usavel.md`), e a documentação desta entrega. Esta entrada não altera código. Números de testes: os do `scripts/check` informados pelo dono e pelo coordenador (frontend: 261 testes em 18 arquivos); contagens por arquivo foram lidas do disco (`def test_` e blocos `it`/`test` por grep). Nenhum total de backend é citado aqui.

## O que foi feito

| Área | Entrega | Onde |
|---|---|---|
| Agrupamento | Série = pasta pai; capítulo com `chapter_number`; ordem natural; `sort_title` com dígitos preenchidos (ADR 0014) | `backend/app/domain/series.py`, `services/scan.py`, `adapters/persistence/series_repository.py` |
| Migrações | `0005` (tabela `series`, `items.series_id`, `items.chapter_number`, backfill), `0006` (`source_url`, `metadata_checked_at`, `title_original`), `0007` (`description_origin` e atribuição); tudo por `ALTER ADD COLUMN`, sem recriar tabelas | `backend/migrations/versions/0005_series.py`, `0006_series_metadata_fields.py`, `0007_series_description_attribution.py` |
| API de séries | `GET /api/v1/series` (lista, busca, paginação), `GET /{id}` (capítulos, progresso do usuário, campo `continue`), `GET /{id}/cover` | `backend/app/api/series.py`, `series_schemas.py`, `services/series_service.py` |
| Metadados | MangaDex e AniList (obra: capa e descrição); Wikipédia pt e Google Livros (só descrição, casamento forte); tradução MyMemory como último recurso, marcada; fusão e estados `none`, `matched`, `manual`, `not_found` (ADR 0015) | `backend/app/services/metadata_service.py`, `enrich_runner.py`, `domain/metadata.py`, `adapters/metadata/*.py` |
| Saída de rede | `SafeGateway`: https, 443, lista fixa de 7 hosts, sem redirecionamento, IP público verificado e conexão fixada, limites, User-Agent genérico | `backend/app/adapters/http/safe_gateway.py` |
| Capas | `DATA_DIR/covers/<uuid>.<ext>`; escrita atômica; servidas pelo app; CSP preservada (ADR 0016) | `backend/app/adapters/storage/cover_store.py`, `backend/app/ports/cover_store.py` |
| Gestão (admin) | `POST /api/v1/library/enrich` (202; `force`), `GET /api/v1/library/enrich/status`, `GET .../metadata/candidates` (10 por minuto por usuário), `POST .../metadata/select`, `PUT` e `DELETE .../metadata` | `backend/app/api/library.py`, `backend/app/api/series.py` |
| CLI | `python -m app.cli enrich [--series <uuid>] [--force]` | `backend/app/cli.py` |
| Configuração | `METADATA_ENABLED`, `METADATA_PROVIDERS`, `METADATA_TRANSLATE_ENABLED`, `METADATA_LANGUAGES`, `METADATA_HTTP_TIMEOUT_SECONDS`, `METADATA_MAX_PER_RUN`, `DATA_DIR` | `backend/app/core/config.py`, `infra/compose.example.yml`, `infra/Dockerfile` (`ENV DATA_DIR=/data`) |
| Frontend: séries | `/serie/:id` com lista de capítulos (busca por número), descrição com origem e atribuição, "continuar", painel de metadados para admin | `frontend/src/features/series/`, `frontend/src/shared/series/` |
| Frontend: leitor | Próximo e anterior capítulo no fim do capítulo; `?serie=` no caminho do leitor; voltar leva à série | `frontend/src/features/reader-manga/components/ChapterEnd.tsx`, `hooks/useReaderNav.ts`, `frontend/src/shared/items/paths.ts` |
| Frontend: biblioteca | Lista de séries (`SeriesCard`); botão "Atualizar metadados" só para admin | `frontend/src/features/library/components/`, `hooks/useLibrary.ts`, `hooks/useEnrich.ts` |
| Correções | `test_reg_020` (capítulos em ordem numérica), `test_reg_021` (edição manual vence enriquecimento em andamento), `test_reg_022` (obra do MangaDex não perdida por edições), `test_reg_023` (espaço após ponto final na tradução) | `backend/tests/regression/` |
| Docs | ADRs 0014, 0015 e 0016; mapas; `AGENTS.md` (regra 7 com a exceção de 2026-11-20); `docs/DEPLOY.md` (seção de DNS no build) | `docs/adr/`, `docs/maps/`, `AGENTS.md`, `docs/DEPLOY.md` |

Decisões: ADR 0014 (agrupamento por pasta), ADR 0015 (metadados de fontes públicas, com autorização do dono de 2026-11-20), ADR 0016 (capas). ADR 0001 a 0013 não foram alterados.

## Validação

| Item | Resultado | Fonte |
|---|---|---|
| `scripts/check` completo | OK (backend e frontend; frontend: 261 testes em 18 arquivos) | Informado pelo coordenador; não reexecutado nesta entrega |
| Imagem Docker | Construída e testada em 2026-11-21 com a biblioteca real | Relatado pelo dono |
| Biblioteca real: séries | Agrupamento e capítulos conferidos | Relatado pelo dono |
| Enriquecimento da série do dono | MangaDex não tem descrição em pt-br; saiu tradução automática do inglês, atribuída ao MangaDex e marcada; capa 512x724 do MangaDex | Relatado pelo dono |
| Navegador | Fluxo validado no navegador com a biblioteca real | Relatado pelo dono (sem reexecução aqui) |
| Migrações | `0001` a `0007` (no disco) | Lido em `backend/migrations/versions/` |
| Import-linter | 8 contratos, sem alteração de regra | Lido em `backend/pyproject.toml` |
| Regressões | `test_reg_001` a `013`, `015` a `023` (no disco); `014` reservado ao FIND-2026-009; próximo livre `024` | Lido em `backend/tests/regression/` |

## Arquivos corrompidos na biblioteca real

| Fato | Detalhe |
|---|---|
| Rejeitados | 92 de 301 arquivos CBZ foram rejeitados como `CorruptArchive` (estrutura ZIP danificada na origem) |
| Comportamento | O app recusa o item em vez de mostrar capítulos quebrados (API: 422 "Item cannot be read") |
| Lacunas | A numeração ficou com buracos onde os arquivos foram recusados |
| Recuperação | Modo de recuperação é opção futura; depende de decisão do dono |

Os números são do dono (a biblioteca real não está no repositório). O comportamento de recusa está em `backend/app/adapters/extractors/cbz.py` (`CorruptArchive`).

## Não validado

| Item | Motivo |
|---|---|
| iOS real (Safari, Tela de Início) | Sem aparelho nesta entrega |
| Service worker e PWA instalável | Não provado; mesmo problema da entrega anterior |
| Proxy, HTTPS e HSTS | Fora de escopo do app; sem proxy real |
| Google Livros de ponta a ponta | Respondeu 429 em todas as tentativas; só testado com respostas canônicas |
| Cota do MyMemory | Não estourada na validação; o limite (cerca de 5 000 caracteres por dia por IP) é a referência |
| Rede do PyPI via DNS filtrado | Falha de build observada em um ambiente; ver `docs/DEPLOY.md` |
| `scripts/check.sh` em Linux real | Testado só com bash do Git no Windows |

## Pendências e riscos conhecidos

| Item | Situação | Próximo passo |
|---|---|---|
| Renomear pasta cria série nova | Limitação aceita (ADR 0014) | Aceitar ou criar chave estável em ADR novo |
| Metadados perdidos ao renomear pasta | Consequência da limitação acima | Reenriquecer com `enrich` |
| Cota do MyMemory | Ao estourar, o tradutor fica quieto por 6 h e a sinopse fica em inglês | Monitorar; avaliar chave própria só com autorização |
| Google Livros 429 | Fonte fica indisponível na prática | Aceitar ou remover da lista |
| Casamento por título | Pode errar em nomes genéricos; admin corrige por `PUT` ou `DELETE` | Revisar após uso |
| Capa fora do backup | `docs/DEPLOY.md` §6 copia só `app.db`; `DATA_DIR/covers` não entra | Incluir `covers/` no backup (decisão do dono) |
| Arquivos corrompidos (92 de 301) | Recusados; lacunas na numeração | Decidir modo de recuperação |
| Filtro por status, reinício de série concluída, mesma série em dois dispositivos | Pendentes (PLANO §9) | Decisão do dono |
| FIND-2026-009 (aberto), M8 (hashes), CI, E2E | Mesmos da entrega anterior | Ver `docs/maps/SECURITY_MAP.md` |
