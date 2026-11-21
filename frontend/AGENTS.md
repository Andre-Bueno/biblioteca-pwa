# frontend/AGENTS.md

React + TypeScript (`strict`) + Vite, PWA. ESLint + Prettier. Organização por feature.

## Estrutura

```
src/
├─ app/        rotas (routes.tsx), providers, registro do service worker, aviso de nova versão
│              (AppUpdatePrompt, useAppUpdate), escolha do leitor (ReaderRoute)
├─ features/   auth · library · series · reader-manga · reader-epub · settings (telas)
│              reader-pdf (esqueleto) · progress (só README)
│   └─ <feature>/{components, hooks, index.ts}   (sem api.ts/types.ts por feature)
└─ shared/     api-client · session · preferences · progress (com flush-registry) · items (com useItem)
               · series (com useReaderNav) · system (versão e aviso) · pwa (estado do SW) · hooks · theme · ui
               offline (só README; único lugar com indexedDB)
```

Dados e chamadas HTTP ficam em `shared/` (`session/api.ts`, `preferences/api.ts`, `progress/api.ts`, `items/api.ts`, `series/api.ts`, `system/api.ts`), porque mais de uma feature usa. Uma feature exporta a tela pelo `index.ts`.

## Regras

- Dependência: `app → features → shared`. **Feature não importa outra feature**; o que for comum vai para `shared/`. Checado por teste de arquitetura.
- Componentes só renderizam; lógica em hooks; chamadas HTTP só via `shared/api-client` ou os `api.ts` de `shared/` (nunca `fetch` solto em componente).
- Tema: tokens de cor em CSS variables; respeitar `prefers-color-scheme`. A preferência é salva no servidor (`PreferencesProvider`); o `ThemeProvider` só guarda o estado em memória.
- Progresso de leitura: enviar com debounce e ao sair/ocultar a página; o servidor é a fonte da verdade. Locator: página (mangá/PDF) ou `capítulo * 10000 + offset_bp` (EPUB). Envio ao ocultar usa `keepalive` pelo `api-client` (nunca `sendBeacon`).
- Sessão: **só 401 em `/auth/me` ou em chamada autenticada (após refresh falho) encerra a sessão local**. 429, 503 e falha de rede mantêm o estado (`error` ou o atual). Refresh rejeitado (401 ou 403 em `/auth/refresh`) encerra a sessão em todo o app.
- Recuperação de imagem (`useImageRecovery`): **nunca chama `/auth/me`**; chama `refreshSession` no máximo uma vez por janela de 60 s, compartilhada por todas as imagens.
- Preferências: `PUT /me/preferences` é sempre o objeto completo montado sobre os dados que o servidor devolveu. **Nunca montar `PUT` a partir de padrões**; alteração feita antes do `GET` responder fica na fila.
- Não usar `localStorage`/`sessionStorage` para nada (ESLint). Estado de leitura e de preferência vem do servidor.
- EPUB renderiza em iframe `sandbox="allow-same-origin"` sem `allow-scripts`, `allow-forms`, `allow-popups` nem `allow-top-navigation` (ADR 0017). O capítulo vem já sanitizado pelo servidor. Proibido `dangerouslySetInnerHTML` com conteúdo não sanitizado.
- Locator de livro: `capítulo * 10000 + offset_bp` (lógica em `features/reader-epub/locator.ts`); progresso de mangá e PDF é página.
- Aviso de nova versão (`shared/system`, `app/AppUpdatePrompt`): **só admin**; nunca mostrado a usuário comum; notas e nomes em texto puro; link só https do GitHub do repositório; consulta de versão no máximo a cada 30 min com a aba visível; acompanhamento após o pedido com 5 s entre consultas e no máximo 60; "Agora não" vale até recarregar. Nenhuma atualização acontece sozinha.
- Service worker em `registerType: 'prompt'`: nova versão espera; **nada recarrega sozinho**. "Recarregar" faz `flushAllProgress` antes de ativar o worker. `skipWaiting` e `clientsClaim` continuam desligados.
- CSRF: enviar o token CSRF em toda requisição que altera estado (centralizado no `api-client`). Tratar `429` (bloqueio por tentativas) com mensagem clara e sem revelar se o usuário existe.
- `credentials`: `same-origin` quando a API está na mesma origem (padrão); `include` só com origem externa configurada. `localStorage` e `sessionStorage` proibidos, inclusive via `window`/`globalThis`/`self` (ESLint).
- Rede e armazenamento: `XMLHttpRequest`, `WebSocket` e `navigator.sendBeacon` só em `shared/api-client`; `indexedDB` só em `shared/offline`; acessos indiretos (alias, desestruturação, `window.navigator.sendBeacon`) não são detectados pelo ESLint e dependem de revisão.
- Service worker: nunca cachear respostas autenticadas de forma que vazem entre usuários; versionar o cache; tokens fora de `localStorage` (usar cookie HttpOnly).
- Leitores devem funcionar com toque (iOS Safari): gestos, safe-area, sem hover obrigatório.
- Séries (`features/series`, dados em `shared/series`): links externos só por `safeHttpsUrl` (https); qualquer outro valor vira texto. Descrição e títulos vindos da rede são texto puro (React escapa); proibido `dangerouslySetInnerHTML` e `innerHTML` nessas telas.
- Atribuição: texto da Wikipédia exibe "CC BY-SA"; texto traduzido mostra o rótulo "tradução automática" e a fonte do original em inglês.
- Painel de metadados (busca, escolher fonte, editar texto, remover) só para `role === 'admin'`; a busca ao vivo só é chamada por ação explícita do admin.
- Capa de série e de item usam URL same-origin (`/api/v1/series/{id}/cover`); nenhum `<img>` aponta para host externo (CSP `img-src 'self'`).
- Nova tela ⇒ linha em `docs/maps/ROUTES.md`.

## Testes

`tests/unit` (hooks/utilitários) · `tests/e2e` (Playwright: login; mangá parar na página 5 e retomar; alternar tema; offline) · `tests/regression` (`reg_NNN`).
