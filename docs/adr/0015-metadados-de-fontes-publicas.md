# ADR 0015: Metadados de fontes públicas (capa e descrição)

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto

- A biblioteca real não tem capa nem sinopse em português; os arquivos têm só o nome.
- A regra 7 de `AGENTS.md` (raiz) proíbe "serviços externos" e "raspar fontes de terceiros" sem autorização do dono.
- O dono autorizou, em 2026-11-20, uma exceção restrita a metadados: consulta de capa e descrição em fontes públicas, com lista fixa de hosts, enviando só o título limpo e a sinopse pública.
- ADR 0002: a segurança é do próprio app; ADR 0003: iOS; ADR 0005: padrões fechados.

## Decisão

| Tema | Decisão |
|---|---|
| Autorização | Exceção à regra 7 da raiz, dada pelo dono em 2026-11-20. Registrada em `AGENTS.md` (regra 7) e em `backend/AGENTS.md`. Não altera outra regra |
| Fontes de obra | MangaDex (capa, descrição pt-br, títulos alternativos) e AniList (capa, descrição em inglês) |
| Fontes só de descrição | Wikipédia pt e Google Livros. Sem capa e sem identidade de obra. Só com casamento forte (limiar 0,9) |
| Tradução | MyMemory, último recurso: tradução automática en→pt-BR da sinopse pública. Sempre marcada como `translated`, com atribuição à fonte original |
| Saída de rede | Só por `SafeGateway` (`adapters/http/safe_gateway.py`): https, porta 443, lista fixa de 7 hosts, sem redirecionamento, sem cookies, User-Agent genérico (`BibliotecaPWA/1.0`), IP público verificado e conexão fixada a ele, limites de tamanho e de tempo, espaçamento de 0,5 s por host |
| Lista fixa | `api.mangadex.org`, `uploads.mangadex.org`, `graphql.anilist.co`, `s4.anilist.co`, `pt.wikipedia.org`, `www.googleapis.com`, `api.mymemory.translated.net`. Não configurável por variável |
| O que sai | Título limpo da série e, para tradução, sinopse já sanitizada e truncada (1 500 caracteres). Nunca caminho, nome de arquivo, id interno ou dado de usuário |
| Desligar | `METADATA_ENABLED=false` troca o gateway por um que não abre socket. Edição manual continua funcionando |
| Casamento | Limiar 0,85 e margem de 0,02 entre o melhor e o segundo; edições ("Book Version", "Doujinshi") penalizadas; em empate, o ano mais antigo; candidato anterior ao ano da obra é descartado. Sem casamento seguro: `not_found`, para o admin decidir |
| Estados | `none`, `matched`, `manual`, `not_found`. Execução automática só mexe em `none` e em `not_found` (após 7 dias). `manual` nunca é sobrescrito, nem com `force` |
| Fusão | Capa e fonte: primeira obra (ordem configurada) cuja capa baixou. Descrição: pt-br de obra; depois pt-br de fonte só-descrição com casamento forte; depois tradução do inglês; por último o texto inglês original, com origem `source` |
| Atribuição | Campos `description_origin`, `description_source_name`, `description_source_url` e `source`. Wikipédia exibe CC BY-SA. Link só https |
| Texto | Descrição sanitizada no domínio (tags, scripts, markdown e controles removidos; até 4 000 caracteres). Exibida como texto puro |
| Cota | Limite por usuário nas buscas ao vivo (10/min). A execução é uma por vez e limitada a `METADATA_MAX_PER_RUN` séries |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Não buscar metadados (só nome do arquivo) | Não atende ao objetivo de capa e sinopse em português |
| Raspar páginas HTML | Viola a regra 7; APIs públicas bastam |
| Chave de API de tradutor pago | Custo e segredo a gerenciar; não autorizado |
| Sinopse em inglês sem tradução | Aceita como último recurso, mas não é o padrão desejado |
| Permitir hosts configuráveis | Abre SSRF; lista fixa no código é mais segura e revisável |
| Fuzzy agressivo | Erro de casamento troca capa de obra; limiar conservador prefere `not_found` |

## Consequências

- Positivas: capa e sinopse para a biblioteca sem serviço próprio; saída de rede pequena, auditável e desligável.
- Negativas e riscos conhecidos:
  - MyMemory (anônimo): cota pública de cerca de 5 000 caracteres por dia por IP. Ao estourar, o tradutor fica quieto por 6 h e a sinopse fica em inglês.
  - Google Livros: respondeu 429 em todas as tentativas no ambiente de validação. Tratado como indisponível; não validado de ponta a ponta.
  - Fontes públicas podem mudar contrato ou sair do ar. Cada resposta é parseada defensivamente.
  - Casamento por título pode errar obras com nomes genéricos; o admin corrige por `PUT`/`DELETE` de metadados.
  - Tradução automática pode ter erro de sentido; por isso é marcada. Um bug de espaço após ponto foi corrigido (REG-023).
- Obrigações:
  - Incluir ou remover host exige ADR novo e teste de allowlist.
  - Qualquer nova saída de rede passa pelo `SafeGateway`.
  - A exceção vale só para metadados; outra integração externa exige nova autorização do dono.

Complementa ADR 0002 e ADR 0016. Não altera ADR 0001 a 0013.

## Emenda 2026-11-21

- **Decisão do dono (2026-11-21, "Sim, igualar"):** a consulta de capa e descrição passa a valer para todos os formatos (EPUB, CBZ, CBR, pasta e PDF), não só para mangá. Séries só de livro deixam de ser puladas.
- **Não muda:** mesmas fontes (lista fixa, sem host novo), mesmos limiares e margens, mesmo `SafeGateway`, mesmo envio (só título limpo e sinopse pública).
- **Efeito:** o casamento por título passa a valer também para livros. Risco de falso positivo em livros com título comum; mitigado pelo estado `manual` (nunca sobrescrito) e pelos limiares (sem casamento seguro: `not_found`).
- **Substituído em:** a regra "séries de livro não entram no enriquecimento" (REG-026 original) foi revogada; o teste REG-026 passa a afirmar o contrário.
- Texto acima da seção "Decisão" permanece como foi aceito.
