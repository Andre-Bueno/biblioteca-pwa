# ADR 0003: PWA para iOS em vez de app nativo

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- O dono usa iPhone e não tem Mac nem conta Apple de desenvolvedor.
- App nativo iOS exige Xcode (Mac) e conta Apple para distribuição.
- Requisitos: leitura de mangá, EPUB e PDF, progresso sincronizado, tema claro/escuro e cache offline do que já foi aberto.

## Decisão

| Tema | Decisão |
|---|---|
| Instalação | PWA: Safari → "Adicionar à Tela de Início" |
| Front | React + TypeScript + Vite, com service worker |
| Migração futura | Se precisar de algo nativo, o front migra para Capacitor sem reescrever |
| Fonte da verdade | Servidor (progresso e biblioteca); cache local é melhor esforço |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| App nativo (Swift) | Exige Mac e conta Apple. |
| React Native / Flutter | Mesmo custo de distribuição iOS, mais stack para manter. |
| Só navegador (sem instalação) | Pior experiência em tela cheia e cache offline mais frágil. |

## Consequências

- Positivas: sem Mac e sem conta Apple; um código para iOS e demais navegadores.
- Trade-offs e riscos (ver `docs/PLANO.md` §10):
  - O Safari pode apagar o armazenamento de sites pouco usados. Instalado na Tela de Início, o risco diminui.
  - Sem download em segundo plano; cota de armazenamento limitada. Offline é "melhor esforço".
  - Push e alguns recursos exigem iOS 16.4+ com o app instalado.
- Obrigação: o progresso nunca depende só do armazenamento local.
