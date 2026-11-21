# Política de segurança

## Versões suportadas

Só a **última release** recebe correções de segurança. Se você usa uma versão mais antiga, atualize antes de reportar (veja `docs/DEPLOY.md`, "Atualizações por release").

## Como reportar uma vulnerabilidade

Reporte de forma **privada**, pelo recurso "Report a vulnerability" do GitHub: aba **Security** do repositório > **Report a vulnerability**. Não abra issue pública, pull request nem discussão com detalhes da falha.

Inclua, se puder: a versão (tag da imagem ou `APP_VERSION`), os passos para reproduzir, o impacto e uma prova de conceito mínima. Não inclua dados reais de pessoas nem segredos.

O projeto é mantido por uma pessoa, sem prazo garantido: a meta é confirmar o recebimento em alguns dias e publicar a correção em uma nova release, com crédito a quem reportou (se quiser).

## Escopo

Dentro do escopo: o código deste repositório e a imagem publicada em `ghcr.io/andre-bueno/biblioteca-pwa`, em especial:

- autenticação, sessão, bloqueio de login, CSRF e limite de requisições;
- leitura de arquivos da biblioteca (CBZ, pasta, EPUB, PDF): path traversal, bombas de descompressão, XSS em conteúdo de livro;
- isolamento entre usuários (acesso a dados de outro usuário);
- injeção (SQL, comandos), SSRF pela busca de metadados e cabeçalhos de segurança;
- o receptor de referência em `infra/deploy-hook/` e os workflows em `.github/`.

Fora do escopo:

- a infraestrutura de quem hospeda: rede, VPN, firewall, TLS, proxy reverso, sistema operacional e o próprio Docker;
- configuração insegura do operador (por exemplo `FORWARDED_ALLOW_IPS=*` com a porta exposta, `COOKIE_SECURE=false` em produção, `SECRET_KEY` fraca);
- vulnerabilidades em dependências já conhecidas e sem exploração no app (acompanhadas pelo Dependabot e pelo `pip-audit`/`npm audit` do CI);
- ataques que exigem acesso físico, conta de administrador já comprometida ou o dispositivo do usuário comprometido;
- ferramentas automáticas sem prova de impacto, spam, engenharia social e negação de serviço por volume bruto de tráfego.

## Recompensa

Não há programa de recompensa (bug bounty) nem pagamento. Não serão aceitos pedidos de pagamento, nem testes contra instâncias de terceiros: teste apenas em uma instância sua.
