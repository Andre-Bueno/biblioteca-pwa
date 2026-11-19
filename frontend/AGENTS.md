# frontend/AGENTS.md

React + TypeScript (`strict`) + Vite, PWA. ESLint + Prettier. Organização por feature.

## Estrutura

```
src/
├─ app/        rotas, providers, registro do service worker
├─ features/   auth · library · reader-manga · reader-epub · reader-pdf · progress · settings
│   └─ <feature>/{components, hooks, api.ts, types.ts}
└─ shared/     ui · theme (claro/escuro/sistema) · api-client · offline
```

## Regras

- Dependência: `app → features → shared`. **Feature não importa outra feature**; o que for comum vai para `shared/`. Checado por teste de arquitetura.
- Componentes só renderizam; lógica em hooks; chamadas HTTP só via `shared/api-client` ou `api.ts` da feature (nunca `fetch` solto em componente).
- Tema: tokens de cor em CSS variables; respeitar `prefers-color-scheme`; preferência salva no servidor.
- Progresso de leitura: enviar com debounce e ao sair/ocultar a página; o servidor é a fonte da verdade. Locator: página (mangá/PDF) ou CFI (EPUB).
- EPUB renderiza em iframe `sandbox` sem `allow-scripts`. Proibido `dangerouslySetInnerHTML` com conteúdo não sanitizado.
- CSRF: enviar o token CSRF em toda requisição que altera estado (centralizado no `api-client`). Tratar `429` (bloqueio por tentativas) com mensagem clara e sem revelar se o usuário existe.
- `credentials`: `same-origin` quando a API está na mesma origem (padrão); `include` só com origem externa configurada. `localStorage` e `sessionStorage` proibidos, inclusive via `window`/`globalThis`/`self` (ESLint).
- Rede e armazenamento: `XMLHttpRequest`, `WebSocket` e `navigator.sendBeacon` só em `shared/api-client`; `indexedDB` só em `shared/offline`; acessos indiretos (alias, desestruturação, `window.navigator.sendBeacon`) não são detectados pelo ESLint e dependem de revisão.
- Service worker: nunca cachear respostas autenticadas de forma que vazem entre usuários; versionar o cache; tokens fora de `localStorage` (usar cookie HttpOnly).
- Leitores devem funcionar com toque (iOS Safari): gestos, safe-area, sem hover obrigatório.
- Nova tela ⇒ linha em `docs/maps/ROUTES.md`.

## Testes

`tests/unit` (hooks/utilitários) · `tests/e2e` (Playwright: login; mangá parar na página 5 e retomar; alternar tema; offline) · `tests/regression` (`reg_NNN`).
