# backend/app/adapters/AGENTS.md

Implementações concretas dos ports. Aqui o código toca disco, arquivos compactados e banco: **principal superfície de ataque**.

## Subpastas
- `persistence/`: repositórios SQLAlchemy (inclui `series_repository.py`). Toda query de dados de usuário filtra por `user_id`.
- `storage/`: acesso ao disco da biblioteca (`LocalStorage`) e às capas baixadas (`cover_store.py`, `DATA_DIR/covers`). Únicos lugares autorizados a resolver caminhos.
- `extractors/`: um arquivo por formato, todos implementando `Extractor` (ou `BookReader`, no caso de livro). Existem: `cbz.py`, `folder.py`, `epub.py` (com `_epub_safe.py`, `_epub_html.py`, `_epub_css.py`), `_common.py`, `registry.py`. Previstos (não existem): `cbr.py`, `pdf.py`.
- `http/`: `safe_gateway.py` (conteúdo e metadados, 8 hosts) e `webhook_notifier.py` (webhook de atualização, única saída fora do gateway; ADR 0018). Só esses dois abrem conexão; ver regras 8 a 11.
- `metadata/`: um provider por fonte (`mangadex.py`, `anilist.py`, `wikipedia.py`, `googlebooks.py`), tradutor `mymemory.py` e `_json.py` (leitura defensiva de JSON da rede). Implementam `MetadataProvider` e `TextTranslator`.

## Regras de segurança
1. Caminho nunca vem do cliente: o cliente envia ID opaco; o storage resolve com `Path.resolve()` e confirma que está dentro da raiz da biblioteca.
2. Arquivos compactados: limitar tamanho total descompactado, nº de entradas e razão de compressão. Ler em memória/stream; nunca extrair para caminho derivado do nome da entrada (zip-slip). Rejeitar links simbólicos e nomes com `..` ou caminho absoluto.
3. CBR (RAR): rodar o extrator externo com timeout, limites de recursos e sem shell; ou converter para CBZ no scan.
4. EPUB: tratar todo o conteúdo como não confiável. O adapter não executa nem interpreta scripts; o capítulo sai sanitizado por allowlist (`_epub_html.py`, `_epub_css.py`), com CSP própria dada pelo middleware (ADR 0017), e o frontend renderiza em iframe `sandbox` sem `allow-scripts`. Fontes e SVG nunca são servidos; DRM é recusado.
5. Metadados (título, nome de arquivo) são texto não confiável: sanitizar antes de expor.
6. Sem `shell=True`, `pickle`, `eval`. Subprocessos só com lista de argumentos.
7. Todo extrator novo vem com testes em `tests/security/` (arquivo malformado, zip bomb, traversal) e linha no `docs/maps/SECURITY_MAP.md`.
8. `SafeGateway`: https, porta 443, sem userinfo, sem literal de IP, host só da lista fixa de 8 (não configurável; `api.github.com` só para `releases/latest`), sem redirecionamento (3xx é erro), IP de destino público e conexão fixada ao IP verificado, TLS com verificação do nome, sem cookies, User-Agent genérico. Limites: JSON 1 MiB, imagem 5 MiB, POST 16 KiB, URL 2 048 caracteres, 0,5 s entre requisições por host.
9. Nenhum adapter novo abre socket por fora do `SafeGateway`, exceto o `webhook_notifier.py` (ADR 0018), cujo destino vem só da configuração. Novo host ou nova saída exige ADR e teste de allowlist ou de destino (`tests/security/test_safe_gateway.py`, `tests/security/test_webhook_notifier.py`).
10. Casamento de metadados: fonte de obra com limiar 0,85 e margem 0,02; fonte só de descrição com limiar 0,9 e sem desempate. Em dúvida, `not_found`.
11. Capa: nome só pelo UUID da série e extensão dos bytes; escrita atômica; nada da rede entra no caminho (`cover_store.py`). Descrição da rede passa por `sanitize_description` antes de ir ao banco.
