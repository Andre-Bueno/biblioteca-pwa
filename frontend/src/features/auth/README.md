# features/auth

Tela de login (`/login`) e guarda de rota (`RequireAuth`). O contexto de sessão (`/auth/me`, login, logout, troca de senha) fica em `src/shared/session/` porque `settings` também o usa. Não importar outras features.
