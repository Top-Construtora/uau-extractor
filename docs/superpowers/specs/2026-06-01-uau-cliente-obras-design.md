# Spec — Fatia 1: Cliente UAU autenticado + slice Obras

- **Data:** 2026-06-01
- **Projeto:** `services/uau-extractor` (submodule de `bi-top-web`)
- **Status:** aprovado (brainstorming) → pronto para implementation plan

## Contexto

O `uau-extractor` extrai dados da API UAU (Trinus/Globaltec) para o BI da TOP, gravando
no Postgres Supabase no schema `uau`, consumido depois pelo `top-dashboards` — o mesmo
papel que o `sienge-bi-shared` cumpre para o ERP Sienge.

A meta de longo prazo é "extrair tudo que for possível da API". Decisões de escopo do
brainstorming que enquadram esta fatia:

1. **Objetivo dos dados:** alimentar dashboards de forma **curada** (modelar `uau.fato_*`/
   `uau.dim_*` só com o necessário), não data lake bruto.
2. **API é orientada a consulta:** endpoints `Consultar*` exigem parâmetros (empresa, obra,
   período). Não há "dump" — "extrair tudo" vira "rodar consultas X com parâmetros Y".
   Portanto o trabalho é fatiado por domínio, cada fatia = seu próprio spec.
3. **Esta fatia (fundação + 1 slice real):** construir o cliente autenticado com lifecycle
   de token + o encanamento de ingestão, provado ponta-a-ponta por **um** domínio real.
4. **Domínio escolhido:** Obras/Engenharia. A TOP tem **apenas 1 obra no UAU que não está
   no Sienge** — logo o volume é pequeno e os parâmetros (empresa+obra) são fixos. Sem
   sobreposição com o Sienge: é justamente a obra que falta lá. Reconciliação entre fontes,
   se necessária, fica a cargo de quem consome (dashboard); o schema `uau` não mistura fontes.
5. **Estratégia de token:** proativo + reativo (opção B abaixo).
6. **Gateway alvo:** **Trinus** (`https://api.trinus.co/uau/v1`), o do "Manual de Integração
   e Autenticação UAU". O Swagger Globaltec
   (`https://snetapi.globaltec.com.br:90/UAUApi_Integracao/swagger/ui/index`) é o catálogo
   de endpoints para descoberta.

## Autenticação (resumo do manual)

Fluxo em 3 camadas (detalhe em `docs/`):

1. **Token de integração** (estático, da Globaltec) → header `X-Integration-Authorization`.
2. **Token do API Gateway Trinus** — OAuth2 `client_credentials`, validade 24h
   (`expires_in: 86400`): `POST {gateway}/oauth/access-token`, header
   `Authorization: Basic <base64(client_id:secret_id)>`, body `{"grant_type":"client_credentials"}`.
3. **Token de usuário UAU** — `POST {api_base}/Autenticador/AutenticarUsuario`, headers
   `client_id` + `access_token` (passo 2) + `X-Integration-Authorization` + `Content-Type`,
   body `{"login":..., "Senha":...}`. TTL **não documentado** no manual.

Chamadas de dados usam os 5 headers + `Authorization: <token_usuario>`.

## Arquitetura / módulos

Preenche o scaffold já existente (stubs `NotImplementedError`):

| Módulo | Responsabilidade |
|---|---|
| `client.py` | `UauClient`: auth + lifecycle de token (B) + `request()`/`post()` com retry |
| `config.py` | `Settings` + `UAU_EMPRESA`, `UAU_OBRA`, margem de expiração de token |
| `extractors/obras.py` | `consultar(client, empresa, obra) -> list[dict]` (endpoint de obra) |
| `transforms/obras.py` | `transformar(registros) -> pandas.DataFrame` (mapeia colunas + tipa) |
| `db.py` | `upsert_dataframe()` idempotente (`ON CONFLICT`, batch 200, schema `uau`) + `hash_linha()` |
| `ingestao.py` | `executar()`: extract → transform → enriquece → upsert → log |
| `sql/migrations/0001_obras.sql` | `CREATE TABLE uau.fato_obra` |

Cada unidade tem propósito único e interface testável isoladamente: o `client` não conhece
obras; os `extractors`/`transforms` não conhecem token; o `db` não conhece a API.

## Lifecycle de token (opção B — proativo + reativo)

Estado no `UauClient`: `_gateway_token`, `_gateway_exp` (epoch), `_user_token`.
**Clock injetável** no construtor (`now: Callable[[], float] = time.time`) para teste determinístico.

- `_ensure_auth()`:
  - gateway ausente **ou** `now() >= _gateway_exp` → renova gateway; grava
    `_gateway_exp = now() + expires_in - MARGEM` (MARGEM = 60 s).
  - user ausente → autentica usuário.
- `request(method, endpoint, json=None)`:
  - `_ensure_auth()`; monta os 5 headers; envia.
  - resposta **401/403** → limpa ambos os tokens, re-autentica a cadeia completa
    (gateway → user), **repete 1 vez**. 401 persistente → levanta erro (credencial inválida).
  - resposta **5xx / timeout** → retry com backoff (3 tentativas).
  - outro **4xx** → levanta erro com o corpo da resposta.
- Tokens guardados **em memória por processo** (cron diário < minutos « 24h). Cache em
  disco/DB para reuso entre runs = fora de escopo.

Isso satisfaz "gerar novo token sempre que necessário": proativo cobre a expiração conhecida
do gateway (24h); reativo (retry em 401) cobre o TTL desconhecido do token de usuário.

## Fluxo de dados (slice Obras)

`ingestao.executar()`:
1. `cfg = config.carregar()`; `client = UauClient(cfg)`.
2. `registros = extractors.obras.consultar(client, cfg.empresa, cfg.obra)`.
3. `df = transforms.obras.transformar(registros)`.
4. Enriquece: `dt_ref` = data do run; `hash_linha` = hash das colunas de identidade.
5. `db.upsert_dataframe(df, "fato_obra", pk_cols=["dt_ref", "hash_linha"])`.
6. Registra log do run (lidas/inseridas/atualizadas/status/erro).

## Schema `uau` (padrão de auditoria do Sienge)

```sql
CREATE SCHEMA IF NOT EXISTS uau;

CREATE TABLE uau.fato_obra (
    dt_ref      date NOT NULL,
    hash_linha  text NOT NULL,
    empresa     text NOT NULL,
    obra        text NOT NULL,
    -- demais colunas finalizadas contra a resposta real do endpoint
    PRIMARY KEY (dt_ref, hash_linha)
);
```

As colunas de negócio são finalizadas na **primeira tarefa de implementação** (ver abaixo),
contra a resposta real da API.

## Primeira tarefa de implementação (resolve o unknown externo)

Antes de modelar/transformar: acessar o Swagger Trinus/Globaltec com a credencial de dev,
**confirmar o endpoint `Consultar*` de obra + seus parâmetros**, e capturar **1 resposta
real** da obra-alvo. A resposta (com segredos removidos) vira:
- a fixture de `test_transform_obras.py`;
- a definição das colunas de `uau.fato_obra` e do `transformar()`.

## Testes (TDD)

- `tests/test_client_token.py` — `httpx.MockTransport` + clock fake (lista de instantes):
  1. primeira chamada autentica gateway + usuário;
  2. segunda chamada dentro do TTL reusa tokens (sem re-auth);
  3. após o clock passar de `_gateway_exp`, renova o gateway proativamente;
  4. chamada de dados retorna 401 uma vez → re-auth full + retry → sucesso;
  5. 401 persistente → levanta erro.
- `tests/test_transform_obras.py` — fixture JSON real → `DataFrame` (shape/colunas/tipos).
- `tests/test_smoke.py` — mantém (import + versão).
- **Run live ponta-a-ponta** = verificação manual (precisa de credencial), documentada no
  README; não é teste automatizado.

## Config / env (adições ao `.env.example`)

- `UAU_EMPRESA` — código da empresa no UAU.
- `UAU_OBRA` — código da obra-alvo (a única obra UAU fora do Sienge).
- (mantém as variáveis de auth e Supabase já existentes.)

## Fora de escopo (próximas fatias)

- Agendamento (cron / GitHub Actions).
- Outros domínios (vendas, financeiro, etc.) — cada um seu spec.
- Rotas/telas para `uau.*` no `top-dashboards`.
- Cache de token persistente (disco/DB) entre runs.
