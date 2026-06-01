# uau-extractor

Extração de dados da **API UAU** (Trinus / Globaltec) para o ecossistema BI da TOP Construtora.

Submodule de [`bi-top-web`](https://github.com/Top-Construtora/bi-top-web). Diferente dos
robôs em `robots/` (RPA Selenium que baixam Excel do Sienge), este serviço consome a API
REST do UAU e grava no Postgres Supabase, no schema **`uau`** — consumido depois pelo
`top-dashboards`.

```
Sienge  → robots/rpa-*  → lib/sienge-bi-shared → Postgres (schema sienge) ┐
                                                                          ├→ top-dashboards
UAU API → services/uau-extractor ───────────────→ Postgres (schema uau)  ┘
```

> **Status:** setup inicial. Esqueleto pronto; a lógica de autenticação, extração e
> ingestão será implementada na próxima fase. Stubs marcados com `NotImplementedError`.

## Estrutura

```
src/uau_extractor/
├── config.py        # carrega .env -> Settings (endpoints + credenciais)
├── client.py        # cliente HTTP UAU/Trinus (fluxo de auth em 3 camadas)
├── extractors/      # 1 módulo por endpoint/relatório da UAUAPi
├── transforms/      # JSON da API -> pandas.DataFrame (formato uau.*)
├── ingestao.py      # orquestrador extract -> transform -> upsert
├── db.py            # engine Postgres + upsert idempotente (schema uau)
├── storage.py       # snapshot opcional do JSON bruto no Supabase Storage
└── sql/
    ├── schema.sql   # CREATE SCHEMA uau
    └── migrations/  # migrations versionadas
docs/                # manual de autenticação (PDF) + links de referência
tests/               # smoke tests
```

## Autenticação (resumo)

Fluxo em 3 camadas (detalhe em `docs/`):

1. **Token de integração** (estático, Globaltec) → header `X-Integration-Authorization`.
2. **Token do API Gateway Trinus** — OAuth2 `client_credentials`, validade 24h:
   `POST {UAU_GATEWAY_URL}/oauth/access-token`.
3. **Token de usuário UAU** — `POST {UAU_API_BASE_URL}/Autenticador/AutenticarUsuario`.

As chamadas de dados usam os headers acima + `Authorization: <token_usuario>`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # + ".[storage]" para o Supabase Storage
cp .env.example .env           # preencher credenciais (entregues por cofre/e-mail)
```

Variáveis de ambiente: ver `.env.example`. Segredos **nunca** vão pro repo (`.env` no `.gitignore`).

## Referências

- Manual de Integração e Autenticação: `docs/`
- Catálogo de endpoints: ver `docs/links.md`
  - Swagger UAUApi: https://snetapi.globaltec.com.br:90/UAUApi_Integracao/swagger/ui/index
  - Ajuda Globaltec: https://ajuda.globaltec.com.br/virtuau/api-de-integracao-rest-para-o-uau-web/
