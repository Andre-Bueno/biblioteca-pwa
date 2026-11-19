# backend/app/adapters/AGENTS.md

Implementações concretas dos ports. Aqui o código toca disco, arquivos compactados e banco: **principal superfície de ataque**.

## Subpastas
- `persistence/`: repositórios SQLAlchemy. Toda query de dados de usuário filtra por `user_id`.
- `storage/`: acesso ao disco da biblioteca (`LocalStorage`). Único lugar autorizado a resolver caminhos.
- `extractors/`: um arquivo por formato (`cbz.py`, `cbr.py`, `folder.py`, `epub.py`, `pdf.py`), todos implementando `Extractor`.

## Regras de segurança
1. Caminho nunca vem do cliente: o cliente envia ID opaco; o storage resolve com `Path.resolve()` e confirma que está dentro da raiz da biblioteca.
2. Arquivos compactados: limitar tamanho total descompactado, nº de entradas e razão de compressão. Ler em memória/stream; nunca extrair para caminho derivado do nome da entrada (zip-slip). Rejeitar links simbólicos e nomes com `..` ou caminho absoluto.
3. CBR (RAR): rodar o extrator externo com timeout, limites de recursos e sem shell; ou converter para CBZ no scan.
4. EPUB: tratar todo o conteúdo como não confiável. O adapter não executa nem interpreta scripts; o frontend renderiza em iframe `sandbox`.
5. Metadados (título, nome de arquivo) são texto não confiável: sanitizar antes de expor.
6. Sem `shell=True`, `pickle`, `eval`. Subprocessos só com lista de argumentos.
7. Todo extrator novo vem com testes em `tests/security/` (arquivo malformado, zip bomb, traversal) e linha no `docs/maps/SECURITY_MAP.md`.
