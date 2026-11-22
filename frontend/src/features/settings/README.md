# features/settings

Tela Ajustes (`/ajustes`): tema, sentido de leitura (via `shared/preferences`), troca de senha e sair (via `shared/session`). Não importar outras features.

Layout: cada bloco é um cartão (`SettingsSection`: ícone SVG inline, título, descrição), com largura máxima de 640 px e safe-area do iOS. Controles segmentados do `shared/ui` ficam em largura total com 48 px de altura dentro dos cartões (override em `settings.css`). "Sobre o app" e "Conta" usam linhas chave/valor (`dl`); o botão Sair usa contorno `--color-danger`. O aviso de versão (`shared/system`) ganha destaque sutil com `--color-accent` só dentro desta tela. Cores só por tokens `--color-*`.
