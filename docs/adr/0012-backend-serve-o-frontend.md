# ADR 0012: Backend serve o frontend (decisão da questão M5)

- **Status:** Aceito
- **Data:** 2026-11-20

## Contexto

- Desde a Fase 0 está em aberto (M5, `docs/PLANO.md` §9): quem serve o HTML da SPA, o FastAPI ou o proxy. A resposta muda a CSP e os cabeçalhos do shell (ADR 0002, ADR 0006).
- Cookies `HttpOnly` de sessão e CSRF (ADR 0008) funcionam sem CORS só na mesma origem.
- O servidor, o proxy e o TLS são do dono e ficam fora do escopo do app (ADR 0002). Não há como o repositório garantir cabeçalhos que o proxy não envia.
- Deploy em um único container (`infra/Dockerfile`, `docs/DEPLOY.md`).

## Decisão

| Tema | Decisão |
|---|---|
| Quem serve | FastAPI, por `backend/app/api/spa.py`, a partir de `FRONTEND_DIST_DIR` (na imagem: `/app/static`) |
| Ativação | Só com `FRONTEND_DIST_DIR` definido. Pasta sem `index.html` impede o app de subir |
| Escopo | Só caminhos fora de `/api`. Caminho `/api/**` desconhecido responde 404 JSON, nunca `index.html` |
| Fallback | Caminho sem extensão que não existe recebe `index.html` (roteamento do cliente). Caminho com extensão que não existe recebe 404 |
| Métodos | GET e HEAD. Outros métodos fora de `/api`: 405 |
| Caminho | Recusa NUL, `\`, `:`, segmento vazio, `.`, `..` e segmento com ponto. Não segue symlink. O arquivo resolvido precisa estar dentro da raiz |
| Cabeçalhos | Os mesmos do `SecurityHeadersMiddleware` (ADR 0006), também nas respostas estáticas |
| CSP | Explícita, sem `unsafe-inline` nem `unsafe-eval`: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` |
| Cache | `assets/*` (nome com hash): `public, max-age=31536000, immutable`. Os demais (`index.html`, `sw.js`, `manifest`): `no-cache`. O fallback nunca recebe cache longo |
| Limites | CSRF e rate limit valem só em `/api`. Arquivo estático não consome o limite da API |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Proxy serve os estáticos | Depende do servidor (fora de escopo); CSP e cabeçalhos ficariam fora do repositório e sem teste |
| Nginx separado no compose | Mais uma imagem e configuração; cabeçalhos em dois lugares |
| Só o servidor de desenvolvimento do Vite | Serve só em desenvolvimento |

## Consequências

- Positivas: mesma origem para API e tela (cookies `Strict`, sem CORS); uma imagem; CSP e caminhos hostis testados (`backend/tests/security/test_spa.py`, `test_security_headers.py`).
- Negativas: o app atende também os arquivos da SPA (carga pequena); trocar o frontend exige reconstruir a imagem.
- Obrigações:
  - Leitor EPUB/PDF que precisar de política diferente exige ADR novo (ADR 0006 continua valendo).
  - Não voltar a aceitar caminho do cliente para o sistema de arquivos.

Este ADR resolve M5. Complementa ADR 0002, ADR 0006 e ADR 0008. Não altera ADR 0001 a 0011.
