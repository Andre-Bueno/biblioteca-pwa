# 2026-11-21 · Redesign visual da tela Ajustes

## O que foi feito
- Tela `/ajustes` (`features/settings`): seções em cartões com ícone SVG (`SettingsSection.tsx`, `SectionIcon.tsx`), largura de 640 px.
- Segmentados de 48 px com trilho com borda; foco por teclado visível no botão selecionado.
- "Sobre o app" e "Conta" em linhas chave/valor; "Sair" em contorno de perigo; aviso de versão com tint de accent; links sem cor padrão do navegador.

## Escopo
- Só frontend, sem commit. Nenhum token alterado, comportamento igual.
- Arquivos: `SettingsPage.tsx`, `ChangePasswordForm.tsx`, `SettingsSection.tsx` (novo), `SectionIcon.tsx` (novo), `settings.css`, `features/settings/README.md`, `CODEMAP.md` e `CHANGELOG.md` (0.1.6).

## Decisões
- Sem ADR novo: mudança visual, sem decisão de arquitetura ou segurança.

## Verificação
- Verificação em navegador (Chromium, larguras 375, 320 e 1280 px, tema claro e escuro).
- Não verificado em iPhone (iOS Safari).

## Pendências
- Verificação em iPhone real.
- Revisão e commit pelo dono.
