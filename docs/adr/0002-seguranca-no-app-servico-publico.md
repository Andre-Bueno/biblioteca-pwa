# ADR 0002: Segurança dentro do app para serviço público na web

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- O app é acessível publicamente pela web.
- Servidor, Docker, rede, VPN/Tailscale, TLS e firewall são configurados fora deste projeto.
- Como não há bloqueio por rede, o app precisa se defender sozinho de qualquer cliente anônimo.
- Premissa de ambiente: o app roda atrás de proxy que termina TLS (cookies `Secure` e IP real por cabeçalho confiável configurável).

## Decisão

| Tema | Decisão |
|---|---|
| Exposição | Serviço público na web |
| Fora de escopo | Rede, VPN, TLS, firewall, bloqueio por IP ou VPN |
| Login | Anti brute force por conta e por IP; atraso progressivo e bloqueio temporário; resposta idêntica para usuário inexistente e senha errada |
| CSRF | Token em toda requisição que altera estado; checagem de `Origin`/`Referer`; CORS com lista fixa |
| Rate limit | Global e por rota (login, scan, páginas) |
| Cabeçalhos | CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Cache-Control em respostas autenticadas, emitidos pelo app |
| Cadastro | Sem cadastro público. Só o dono cria contas (CLI/script ou endpoint exclusivo de admin). Sem "registrar" nem "esqueci a senha" abertos |

Detalhes de ameaças e controles em `docs/PLANO.md` §6.

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Confiar na VPN/rede privada | Premissa do dono: o app é público. Controle fora do app não conta como defesa. |
| Cadastro público com verificação de e-mail | Aumenta superfície de abuso e exige serviço externo de e-mail, proibido sem autorização. |

## Consequências

- Positivas: o app é seguro isoladamente; cada controle tem teste em `backend/tests/security`.
- Negativas: mais código de borda (rate limit, CSRF, bloqueio) e necessidade de testes de segurança contínuos.
- Obrigações: não desligar verificações de segurança nem CI; todo finding corrigido ganha teste `test_reg_<NNN>_<slug>`.
- Pendente: reset de senha feito pelo admin; CAPTCHA opcional após limite (sem serviço externo sem autorização).
