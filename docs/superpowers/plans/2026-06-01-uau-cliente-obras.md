# Cliente UAU + Slice Obras — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o cliente HTTP autenticado da API UAU/Trinus com lifecycle de token (proativo + reativo) e o encanamento de ingestão, provado ponta-a-ponta extraindo a obra UAU-only para `uau.fato_obra`.

**Architecture:** Pacote Python `uau_extractor` (layout `src/`). O `UauClient` encapsula o fluxo de 3 tokens (integração estático + gateway OAuth2 24h + token de usuário) e expõe `post(endpoint, payload)` com renovação automática. `db.py` faz upsert idempotente no schema `uau`. `extractors`/`transforms`/`ingestao` ligam a API ao Postgres. O cliente não conhece domínio; extractors/transforms não conhecem token; db não conhece a API.

**Tech Stack:** Python 3.11+, httpx (HTTP + `MockTransport` nos testes), pandas, SQLAlchemy 2 + psycopg2 (Postgres Supabase), pytest, ruff.

**Diretório de trabalho:** todos os caminhos são relativos a `services/uau-extractor/`. Rodar `git`/`pytest` a partir daí. Ative o venv: `source .venv/bin/activate`.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Fase |
|---|---|---|
| `src/uau_extractor/config.py` (modificar) | + `empresa`, `obra`, `token_margem_s` | A |
| `src/uau_extractor/client.py` (reescrever) | auth + lifecycle de token + `request`/`post` + retry | A |
| `src/uau_extractor/db.py` (reescrever) | `hash_linha`, `em_lotes`, `upsert_dataframe` (schema `uau`) | A |
| `tests/test_client_token.py` (criar) | lifecycle de token via `MockTransport` + clock fake | A |
| `tests/test_db.py` (criar) | `hash_linha` + `em_lotes` | A |
| `tests/conftest.py` (criar) | helpers: `make_settings`, `FakeApi`, `Clock` | A |
| `.env.example` (modificar) | + `UAU_EMPRESA`, `UAU_OBRA`, `UAU_TOKEN_MARGEM_S`, `UAU_ENDPOINT_OBRA` | A |
| `scripts/probe_obra.py` (criar) | descobre endpoint + salva amostra real (precisa `.env`) | B |
| `tests/fixtures/obra_sample.json` (criar via probe) | resposta real scrubbed → fixture | B |
| `src/uau_extractor/sql/migrations/0001_obras.sql` (criar) | `CREATE TABLE uau.fato_obra` | B |
| `src/uau_extractor/transforms/obras.py` (criar) | JSON → DataFrame | B |
| `src/uau_extractor/extractors/obras.py` (criar) | chama o endpoint de obra | B |
| `src/uau_extractor/ingestao.py` (reescrever) | `executar()` orquestra o slice | B |
| `tests/test_transform_obras.py` (criar) | fixture → DataFrame | B |

---

# FASE A — Núcleo independente de credencial (executável já)

## Task 1: Config — empresa, obra, margem de token

**Files:**
- Modify: `src/uau_extractor/config.py`
- Test: `tests/test_config_extra.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_config_extra.py
import os
from uau_extractor.config import carregar


def test_carregar_le_empresa_obra_margem(monkeypatch):
    for k in ("UAU_TOKEN_INTEGRACAO", "UAU_CLIENT_ID", "UAU_TRINUS_BASIC",
              "UAU_LOGIN", "UAU_SENHA"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("UAU_EMPRESA", "1")
    monkeypatch.setenv("UAU_OBRA", "42")
    monkeypatch.setenv("UAU_TOKEN_MARGEM_S", "90")
    cfg = carregar()
    assert cfg.empresa == "1"
    assert cfg.obra == "42"
    assert cfg.token_margem_s == 90


def test_token_margem_default_60(monkeypatch):
    for k in ("UAU_TOKEN_INTEGRACAO", "UAU_CLIENT_ID", "UAU_TRINUS_BASIC",
              "UAU_LOGIN", "UAU_SENHA"):
        monkeypatch.setenv(k, "x")
    monkeypatch.delenv("UAU_TOKEN_MARGEM_S", raising=False)
    assert carregar().token_margem_s == 60
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_config_extra.py -v`
Expected: FAIL (`Settings` não tem `empresa`/`obra`/`token_margem_s`).

- [ ] **Step 3: Implementar**

Em `src/uau_extractor/config.py`, adicionar campos ao dataclass `Settings` (depois de `senha`, antes de `db_url`):

```python
    # Alvo da extração de obras
    empresa: str = ""
    obra: str = ""
    # Margem (s) subtraída da expiração do token de gateway
    token_margem_s: int = 60
```

E em `carregar()`, adicionar ao construtor de `Settings` (antes de `db_url=`):

```python
        empresa=os.environ.get("UAU_EMPRESA", ""),
        obra=os.environ.get("UAU_OBRA", ""),
        token_margem_s=int(os.environ.get("UAU_TOKEN_MARGEM_S", "60")),
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_config_extra.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/uau_extractor/config.py tests/test_config_extra.py
git commit -m "feat(config): empresa, obra e margem de token"
```

---

## Task 2: Fixtures de teste (helpers do cliente)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Escrever os helpers** (sem teste próprio — são infra de teste, exercitados nas Tasks 3-7)

```python
# tests/conftest.py
import httpx

from uau_extractor.config import Settings


def make_settings(**over):
    base = dict(
        gateway_url="https://gw.test",
        api_base_url="https://api.test/uau/v1",
        token_integracao="INTEG",
        client_id="CID",
        trinus_basic="BASIC",
        login="user",
        senha="pw",
        token_margem_s=60,
    )
    base.update(over)
    return Settings(**base)


class Clock:
    """Relógio fake injetável; mude `.t` para avançar o tempo."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeApi:
    """Backend httpx fake para o gateway, auth de usuário e endpoint de dados."""

    def __init__(self):
        self.gateway_calls = 0
        self.user_calls = 0
        self.data_calls = 0
        self.data_responses = []  # fila de (status_code, json_body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access-token"):
            self.gateway_calls += 1
            return httpx.Response(200, json={
                "access_token": f"GW{self.gateway_calls}",
                "token_type": "access_token",
                "expires_in": 86400,
            })
        if path.endswith("/Autenticador/AutenticarUsuario"):
            self.user_calls += 1
            return httpx.Response(200, json={"token": f"USR{self.user_calls}"})
        # endpoint de dados
        self.data_calls += 1
        if self.data_responses:
            status, body = self.data_responses.pop(0)
        else:
            status, body = 200, [{"ok": True}]
        return httpx.Response(status, json=body)

    def transport(self):
        return httpx.MockTransport(self.handler)
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test: helpers de teste do cliente (FakeApi, Clock, make_settings)"
```

---

## Task 3: Cliente — autentica na primeira chamada

**Files:**
- Modify: `src/uau_extractor/client.py`
- Test: `tests/test_client_token.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_client_token.py
import httpx
import pytest

from tests.conftest import Clock, FakeApi, make_settings
from uau_extractor.client import UauClient, UauAuthError


def build(api, clock=None):
    return UauClient(
        make_settings(),
        now=clock or Clock(),
        transport=api.transport(),
        sleep=lambda _s: None,
    )


def test_autentica_gateway_e_usuario_na_primeira_chamada():
    api = FakeApi()
    c = build(api)
    r = c.post("Obra/Consultar", {})
    assert r.status_code == 200
    assert api.gateway_calls == 1
    assert api.user_calls == 1
    assert api.data_calls == 1
    c.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_client_token.py -v`
Expected: FAIL (`UauClient` ainda é o esqueleto / faltam `UauAuthError`, `now`, `transport`, `sleep`).

- [ ] **Step 3: Reescrever `src/uau_extractor/client.py`**

```python
"""Cliente HTTP da API UAU/Trinus com lifecycle de token (proativo + reativo).

Fluxo de auth em 3 camadas (ver docs/"Manual de Integração e Autenticação UAU.pdf"):
1. Token de integração (estático)        -> header X-Integration-Authorization
2. Token do API Gateway (OAuth2, 24h)     -> POST {gateway_url}/oauth/access-token
3. Token de usuário UAU                    -> POST {api_base_url}/Autenticador/AutenticarUsuario

Chamadas de dados usam os 5 headers + Authorization: <token_usuario>.
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

from .config import Settings


class UauAuthError(RuntimeError):
    """Falha de autenticação (gateway, usuário, ou 401/403 persistente)."""


def _extrair_token_usuario(payload) -> str:
    """Extrai o token de usuário da resposta de AutenticarUsuario.

    Tolerante a variações de chave; a chave real é confirmada na descoberta (Fase B).
    """
    if isinstance(payload, str) and payload:
        return payload
    if isinstance(payload, dict):
        for k in ("token", "Token", "access_token", "tokenUsuario", "TokenUsuario"):
            valor = payload.get(k)
            if valor:
                return str(valor)
    raise UauAuthError(f"token de usuário não encontrado na resposta: {payload!r}")


class UauClient:
    def __init__(
        self,
        settings: Settings,
        *,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.s = settings
        self._now = now
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._max_retries = max_retries
        self._gateway_token: str | None = None
        self._gateway_exp: float = 0.0
        self._user_token: str | None = None

    # --- passo 2: gateway ---
    def _auth_gateway(self) -> None:
        r = self._http.post(
            f"{self.s.gateway_url}/oauth/access-token",
            headers={"Authorization": f"Basic {self.s.trinus_basic}",
                     "Content-Type": "application/json"},
            json={"grant_type": "client_credentials"},
        )
        if r.status_code != 200:
            raise UauAuthError(f"auth do gateway falhou: {r.status_code} {r.text}")
        data = r.json()
        self._gateway_token = data["access_token"]
        expira = int(data.get("expires_in", 86400))
        self._gateway_exp = self._now() + expira - self.s.token_margem_s

    # --- passo 3: usuário ---
    def _auth_user(self) -> None:
        r = self._http.post(
            f"{self.s.api_base_url}/Autenticador/AutenticarUsuario",
            headers={
                "client_id": self.s.client_id,
                "access_token": self._gateway_token or "",
                "X-Integration-Authorization": self.s.token_integracao,
                "Content-Type": "application/json",
            },
            json={"login": self.s.login, "Senha": self.s.senha},
        )
        if r.status_code != 200:
            raise UauAuthError(f"auth de usuário falhou: {r.status_code} {r.text}")
        self._user_token = _extrair_token_usuario(r.json())

    def _ensure_auth(self) -> None:
        if self._gateway_token is None or self._now() >= self._gateway_exp:
            self._auth_gateway()
            self._user_token = None  # gateway novo -> usuário também renova
        if self._user_token is None:
            self._auth_user()

    def _headers_dados(self) -> dict:
        return {
            "client_id": self.s.client_id,
            "access_token": self._gateway_token or "",
            "X-Integration-Authorization": self.s.token_integracao,
            "Content-Type": "application/json",
            "Authorization": self._user_token or "",
        }

    def _enviar(self, method: str, url: str, json) -> httpx.Response:
        ultimo: object = None
        for tentativa in range(self._max_retries):
            try:
                r = self._http.request(method, url, headers=self._headers_dados(), json=json)
            except httpx.TransportError as e:
                ultimo = e
                self._sleep(0.5 * (tentativa + 1))
                continue
            if r.status_code >= 500:
                ultimo = r
                self._sleep(0.5 * (tentativa + 1))
                continue
            return r
        if isinstance(ultimo, httpx.Response):
            return ultimo
        raise UauAuthError(f"falha de transporte após {self._max_retries} tentativas: {ultimo}")

    def request(self, method: str, endpoint: str, json=None) -> httpx.Response:
        url = f"{self.s.api_base_url}/{endpoint.lstrip('/')}"
        self._ensure_auth()
        r = self._enviar(method, url, json)
        if r.status_code in (401, 403):
            self._gateway_token = None
            self._user_token = None
            self._ensure_auth()
            r = self._enviar(method, url, json)
            if r.status_code in (401, 403):
                raise UauAuthError(f"401/403 após re-autenticação: {r.text}")
        r.raise_for_status()
        return r

    def post(self, endpoint: str, payload: dict) -> httpx.Response:
        return self.request("POST", endpoint, json=payload)

    def close(self) -> None:
        self._http.close()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_client_token.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/uau_extractor/client.py tests/test_client_token.py
git commit -m "feat(client): auth de gateway + usuário na primeira chamada"
```

---

## Task 4: Cliente — reusa token dentro do TTL

**Files:**
- Modify: `tests/test_client_token.py`

- [ ] **Step 1: Escrever o teste que falha** (adicionar ao fim do arquivo)

```python
def test_reusa_token_dentro_do_ttl():
    api = FakeApi()
    c = build(api, Clock(1000.0))
    c.post("Obra/Consultar", {})
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 1   # não re-autenticou
    assert api.user_calls == 1
    assert api.data_calls == 2
    c.close()
```

- [ ] **Step 2: Rodar**

Run: `pytest tests/test_client_token.py::test_reusa_token_dentro_do_ttl -v`
Expected: PASS (a implementação da Task 3 já cobre; este teste trava o comportamento).

- [ ] **Step 3: Commit**

```bash
git add tests/test_client_token.py
git commit -m "test(client): reuso de token dentro do TTL"
```

---

## Task 5: Cliente — renova gateway proativamente após expirar

**Files:**
- Modify: `tests/test_client_token.py`

- [ ] **Step 1: Escrever o teste que falha** (adicionar ao fim)

```python
def test_renova_gateway_apos_expirar():
    api = FakeApi()
    clock = Clock(1000.0)
    c = build(api, clock)
    c.post("Obra/Consultar", {})        # gateway_exp = 1000 + 86400 - 60
    clock.t = 1000.0 + 86400            # passou da expiração (margem 60s)
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 2       # renovou o gateway
    assert api.user_calls == 2          # usuário também renovou
    c.close()
```

- [ ] **Step 2: Rodar e ver passar**

Run: `pytest tests/test_client_token.py::test_renova_gateway_apos_expirar -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_client_token.py
git commit -m "test(client): renovação proativa do gateway na expiração"
```

---

## Task 6: Cliente — retry reativo em 401

**Files:**
- Modify: `tests/test_client_token.py`

- [ ] **Step 1: Escrever os testes que falham** (adicionar ao fim)

```python
def test_retry_apos_401_reautentica():
    api = FakeApi()
    api.data_responses = [(401, {"msg": "expirado"})]  # 1ª de dados falha; 2ª usa default 200
    c = build(api)
    r = c.post("Obra/Consultar", {})
    assert r.status_code == 200
    assert api.gateway_calls == 2   # re-auth completo
    assert api.user_calls == 2
    assert api.data_calls == 2      # original + retry
    c.close()


def test_401_persistente_levanta():
    api = FakeApi()
    api.data_responses = [(401, {}), (401, {})]
    c = build(api)
    with pytest.raises(UauAuthError):
        c.post("Obra/Consultar", {})
    c.close()
```

- [ ] **Step 2: Rodar e ver passar**

Run: `pytest tests/test_client_token.py -v`
Expected: PASS (todos os testes do arquivo).

- [ ] **Step 3: Commit**

```bash
git add tests/test_client_token.py
git commit -m "test(client): re-auth reativo em 401 e erro em 401 persistente"
```

---

## Task 7: Cliente — retry em 5xx

**Files:**
- Modify: `tests/test_client_token.py`

- [ ] **Step 1: Escrever o teste que falha** (adicionar ao fim)

```python
def test_retry_em_500():
    api = FakeApi()
    api.data_responses = [(500, {"erro": "instável"}), (200, [{"ok": 1}])]
    c = build(api)
    r = c.post("Obra/Consultar", {})
    assert r.status_code == 200
    assert api.gateway_calls == 1   # 5xx não re-autentica
    assert api.data_calls == 2
    c.close()
```

- [ ] **Step 2: Rodar e ver passar**

Run: `pytest tests/test_client_token.py::test_retry_em_500 -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_client_token.py
git commit -m "test(client): retry em respostas 5xx"
```

---

## Task 8: db — hash_linha e em_lotes

**Files:**
- Modify: `src/uau_extractor/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_db.py
from uau_extractor.db import em_lotes, hash_linha


def test_hash_linha_deterministico():
    assert hash_linha(["1", "42", "x"]) == hash_linha(["1", "42", "x"])


def test_hash_linha_muda_com_valor():
    assert hash_linha(["1", "42"]) != hash_linha(["1", "43"])


def test_hash_linha_trata_none():
    # None e "" colapsam para vazio; não deve levantar
    assert hash_linha([None, "a"]) == hash_linha(["", "a"])


def test_em_lotes_divide_em_blocos():
    assert list(em_lotes(list(range(5)), 2)) == [[0, 1], [2, 3], [4]]


def test_em_lotes_lista_vazia():
    assert list(em_lotes([], 2)) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_db.py -v`
Expected: FAIL (`em_lotes`/`hash_linha` não existem).

- [ ] **Step 3: Reescrever `src/uau_extractor/db.py`**

```python
"""Acesso ao Postgres (Supabase): engine + upsert idempotente no schema `uau`.

Espelha o padrão de lib/sienge-bi-shared (search_path, batch p/ pooler PgBouncer),
adaptado para o schema `uau`.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Iterable, Iterator, Sequence

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

SCHEMA = "uau"


@lru_cache(maxsize=1)
def get_engine(db_url: str) -> Engine:
    """Engine singleton com tuning Supabase (search_path=uau,public, pool_recycle)."""
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"options": f"-csearch_path={SCHEMA},public"},
    )


def hash_linha(valores: Sequence) -> str:
    """SHA-256 das colunas de identidade; None e '' colapsam para vazio."""
    base = "|".join("" if v is None else str(v) for v in valores)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def em_lotes(seq: list, n: int = 200) -> Iterator[list]:
    """Fatiar uma lista em blocos de tamanho n."""
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def upsert_dataframe(
    engine: Engine,
    df: pd.DataFrame,
    tabela: str,
    pk_cols: list[str],
    batch_size: int = 200,
) -> dict:
    """Upsert idempotente de um DataFrame em uau.<tabela> via ON CONFLICT DO UPDATE.

    Retorna {"lidas": N, "afetadas": M}. Verificado contra Postgres no run manual (Task 14).
    """
    if df.empty:
        return {"lidas": 0, "afetadas": 0}
    meta = MetaData()
    tbl = Table(tabela, meta, schema=SCHEMA, autoload_with=engine)
    registros = df.where(pd.notnull(df), None).to_dict(orient="records")
    afetadas = 0
    update_cols = [c for c in df.columns if c not in pk_cols]
    with engine.begin() as conn:
        for lote in em_lotes(registros, batch_size):
            stmt = pg_insert(tbl).values(lote)
            stmt = stmt.on_conflict_do_update(
                index_elements=pk_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
            conn.execute(stmt)
            afetadas += len(lote)
    return {"lidas": len(registros), "afetadas": afetadas}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_db.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/uau_extractor/db.py tests/test_db.py
git commit -m "feat(db): hash_linha, em_lotes e upsert_dataframe no schema uau"
```

---

## Task 9: Atualizar `.env.example` + rodar a suíte toda

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Adicionar variáveis** ao `.env.example`, na seção UAU (após `UAU_SENHA`):

```bash
# Alvo da extração de obras (a obra UAU que não está no Sienge)
UAU_EMPRESA=
UAU_OBRA=
# Margem (segundos) subtraída da expiração do token de gateway
UAU_TOKEN_MARGEM_S=60
# Endpoint Consultar* de obra (confirmar no Swagger — ver scripts/probe_obra.py)
UAU_ENDPOINT_OBRA=
```

- [ ] **Step 2: Rodar a suíte completa + ruff**

Run: `ruff check src && pytest -q`
Expected: PASS — todos os testes (smoke + config + client + db) verdes, ruff limpo.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(env): variáveis de obra, margem de token e endpoint"
```

**>>> Fim da Fase A: cliente autenticado + db testados e commitados. <<<**

---

# FASE B — Slice Obras (portão de descoberta: precisa de credencial)

> A Fase B precisa de um `.env` preenchido com credenciais reais (entregues por cofre/e-mail)
> e acesso ao Swagger. As Tasks 11–13 só ficam concretas **depois** que a Task 10 salvar a
> amostra real — as colunas de `uau.fato_obra` e o `transformar()` derivam dela.

## Task 10: Descoberta — probe do endpoint + amostra real

**Files:**
- Create: `scripts/probe_obra.py`
- Create (gerado): `tests/fixtures/obra_sample.json`

- [ ] **Step 1: Criar o script de probe**

```python
# scripts/probe_obra.py
"""Probe de descoberta: autentica e chama o endpoint de obra, salvando a resposta.

Uso (com .env preenchido):
    python scripts/probe_obra.py

Confirme UAU_ENDPOINT_OBRA no Swagger antes de rodar:
    https://snetapi.globaltec.com.br:90/UAUApi_Integracao/swagger/ui/index
O payload de consulta (parâmetros como empresa/obra) também sai do Swagger — ajuste PAYLOAD.
"""
import json
import os
from pathlib import Path

from uau_extractor.client import UauClient
from uau_extractor.config import carregar

DESTINO = Path("tests/fixtures/obra_sample.json")


def main() -> None:
    cfg = carregar()
    endpoint = os.environ["UAU_ENDPOINT_OBRA"]  # ex.: "Obras/ConsultarObras"
    payload = {"empresa": cfg.empresa, "obra": cfg.obra}  # ajustar aos params reais
    c = UauClient(cfg)
    try:
        resp = c.post(endpoint, payload)
        dados = resp.json()
    finally:
        c.close()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — {len(dados) if isinstance(dados, list) else 1} registro(s) salvos em {DESTINO}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Confirmar endpoint + parâmetros no Swagger**

Abrir o Swagger, localizar o serviço de **Obra** e o método `Consultar*`. Anotar:
- o caminho (ex.: `Obras/ConsultarObras`) → preencher `UAU_ENDPOINT_OBRA` no `.env`;
- os parâmetros obrigatórios do body → ajustar `PAYLOAD` no script se diferirem de `{empresa, obra}`;
- a chave do token na resposta de `AutenticarUsuario` → se não for uma das cobertas por
  `_extrair_token_usuario`, adicionar a chave real à lista naquele helper (`client.py`).

- [ ] **Step 3: Rodar o probe** (precisa `.env` com credenciais reais)

Run: `python scripts/probe_obra.py`
Expected: imprime "OK — N registro(s)..." e cria `tests/fixtures/obra_sample.json`.
Se vier 401/403 → revisar credenciais; se 404 → endpoint errado, voltar ao Swagger.

- [ ] **Step 4: Scrub + inspeção**

Abrir `tests/fixtures/obra_sample.json`. Remover qualquer dado sensível que não seja
necessário ao teste. **Anotar os nomes/typos dos campos** — eles definem as Tasks 11–13.

- [ ] **Step 5: Commit**

```bash
git add scripts/probe_obra.py tests/fixtures/obra_sample.json
git commit -m "chore(obras): script de probe + amostra real do endpoint"
```

---

## Task 11: Schema `uau.fato_obra`

**Files:**
- Create: `src/uau_extractor/sql/migrations/0001_obras.sql`

- [ ] **Step 1: Escrever a migration** a partir dos campos do fixture (Task 10).

Padrão fixo (sempre presente): `dt_ref`, `hash_linha`, `empresa`, `obra` + PK de auditoria.
Adicionar uma coluna por campo de negócio do fixture, com o tipo Postgres adequado
(`text` para strings/códigos, `numeric` para valores, `date`/`timestamptz` para datas).

Exemplo (substituir as colunas de negócio pelas **reais** do fixture):

```sql
-- 0001_obras.sql — tabela fato da extração de obras do UAU.
CREATE SCHEMA IF NOT EXISTS uau;

CREATE TABLE IF NOT EXISTS uau.fato_obra (
    dt_ref      date NOT NULL,
    hash_linha  text NOT NULL,
    empresa     text NOT NULL,
    obra        text NOT NULL,
    -- >>> colunas de negócio do fixture (exemplo a ajustar): <<<
    descricao        text,
    status           text,
    data_inicio      date,
    percentual_obra  numeric,
    PRIMARY KEY (dt_ref, hash_linha)
);
```

- [ ] **Step 2: Aplicar no Postgres de teste/Supabase**

Run: `psql "$SUPABASE_DB_URL" -f src/uau_extractor/sql/migrations/0001_obras.sql`
Expected: `CREATE SCHEMA` / `CREATE TABLE` sem erro.

- [ ] **Step 3: Commit**

```bash
git add src/uau_extractor/sql/migrations/0001_obras.sql
git commit -m "feat(sql): tabela uau.fato_obra"
```

---

## Task 12: Transform — JSON → DataFrame

**Files:**
- Create: `src/uau_extractor/transforms/obras.py`
- Test: `tests/test_transform_obras.py`

- [ ] **Step 1: Escrever o teste que falha** usando o fixture real.

```python
# tests/test_transform_obras.py
import json
from pathlib import Path

import pandas as pd

from uau_extractor.transforms.obras import COLUNAS, transformar

FIXTURE = Path("tests/fixtures/obra_sample.json")


def _registros():
    dados = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return dados if isinstance(dados, list) else [dados]


def test_transformar_retorna_dataframe_com_colunas():
    df = transformar(_registros())
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == COLUNAS
    assert len(df) == len(_registros())


def test_transformar_lista_vazia():
    df = transformar([])
    assert list(df.columns) == COLUNAS
    assert df.empty
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_transform_obras.py -v`
Expected: FAIL (módulo `transforms.obras` não existe).

- [ ] **Step 3: Implementar** mapeando os campos do fixture (substituir o mapa de exemplo).

```python
# src/uau_extractor/transforms/obras.py
"""Transforma a resposta do endpoint de obra do UAU em DataFrame de uau.fato_obra."""
from __future__ import annotations

import pandas as pd

# Colunas de negócio (sem dt_ref/hash_linha, adicionadas na ingestão).
# AJUSTAR aos campos reais do fixture (tests/fixtures/obra_sample.json).
COLUNAS = ["empresa", "obra", "descricao", "status", "data_inicio", "percentual_obra"]

# Mapa coluna_destino -> chave no JSON da API. AJUSTAR às chaves reais.
_MAPA = {
    "empresa": "Empresa",
    "obra": "Obra",
    "descricao": "Descricao",
    "status": "Status",
    "data_inicio": "DataInicio",
    "percentual_obra": "PercentualObra",
}


def transformar(registros: list[dict]) -> pd.DataFrame:
    linhas = [{dest: r.get(orig) for dest, orig in _MAPA.items()} for r in registros]
    df = pd.DataFrame(linhas, columns=COLUNAS)
    # tipagem mínima (ajustar conforme os campos reais):
    if "data_inicio" in df:
        df["data_inicio"] = pd.to_datetime(df["data_inicio"], errors="coerce").dt.date
    if "percentual_obra" in df:
        df["percentual_obra"] = pd.to_numeric(df["percentual_obra"], errors="coerce")
    return df
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_transform_obras.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/uau_extractor/transforms/obras.py tests/test_transform_obras.py
git commit -m "feat(transforms): obra JSON -> DataFrame"
```

---

## Task 13: Extractor + ingestão

**Files:**
- Create: `src/uau_extractor/extractors/obras.py`
- Modify: `src/uau_extractor/ingestao.py`

- [ ] **Step 1: Criar o extractor**

```python
# src/uau_extractor/extractors/obras.py
"""Extractor de obras: chama o endpoint Consultar* e devolve a lista de registros."""
from __future__ import annotations

import os

from ..client import UauClient


def consultar(client: UauClient, empresa: str, obra: str) -> list[dict]:
    endpoint = os.environ["UAU_ENDPOINT_OBRA"]
    payload = {"empresa": empresa, "obra": obra}  # alinhar com o probe (Task 10)
    dados = client.post(endpoint, payload).json()
    return dados if isinstance(dados, list) else [dados]
```

- [ ] **Step 2: Reescrever `ingestao.py`**

```python
# src/uau_extractor/ingestao.py
"""Orquestrador de ingestão UAU: extract (API) -> transform -> upsert (uau.fato_obra)."""
from __future__ import annotations

import datetime as dt

from . import db
from .client import UauClient
from .config import carregar
from .extractors import obras as ex_obras
from .transforms import obras as tr_obras


def executar() -> dict:
    cfg = carregar()
    client = UauClient(cfg)
    try:
        registros = ex_obras.consultar(client, cfg.empresa, cfg.obra)
    finally:
        client.close()

    df = tr_obras.transformar(registros)
    df.insert(0, "dt_ref", dt.date.today())
    df.insert(1, "hash_linha", [
        db.hash_linha([r["empresa"], r["obra"]]) for r in df.to_dict(orient="records")
    ])

    engine = db.get_engine(cfg.db_url)
    resultado = db.upsert_dataframe(engine, df, "fato_obra", pk_cols=["dt_ref", "hash_linha"])
    print(f"ingestão obras: {resultado}")
    return resultado


if __name__ == "__main__":
    executar()
```

> Nota: `hash_linha` usa as colunas de identidade do negócio. Se a obra tiver mais de uma
> linha por extração (ex.: medições), incluir os campos que as distinguem na lista do hash.

- [ ] **Step 3: Rodar ruff + suíte (sem tocar na rede)**

Run: `ruff check src && pytest -q`
Expected: PASS — testes de Fase A + transform; o extractor/ingestão não roda em teste (precisa de rede), só importa.

- [ ] **Step 4: Commit**

```bash
git add src/uau_extractor/extractors/obras.py src/uau_extractor/ingestao.py
git commit -m "feat(obras): extractor + orquestrador de ingestão"
```

---

## Task 14: Verificação ponta-a-ponta (manual, com credenciais)

**Files:** nenhum (verificação).

- [ ] **Step 1: Garantir `.env` preenchido** (credenciais + `UAU_EMPRESA`/`UAU_OBRA`/`UAU_ENDPOINT_OBRA`) e schema aplicado (Task 11).

- [ ] **Step 2: Rodar a ingestão de verdade**

Run: `python -m uau_extractor.ingestao`
Expected: imprime `ingestão obras: {'lidas': N, 'afetadas': N}` sem erro.

- [ ] **Step 3: Conferir no Postgres**

Run: `psql "$SUPABASE_DB_URL" -c "SELECT dt_ref, empresa, obra FROM uau.fato_obra;"`
Expected: a obra-alvo presente.

- [ ] **Step 4: Rodar de novo e confirmar idempotência**

Run: `python -m uau_extractor.ingestao` (de novo)
Expected: `afetadas` igual; sem linhas duplicadas (`SELECT count(*)` estável para o mesmo `dt_ref`).

- [ ] **Step 5: Atualizar README + bump do ponteiro no parent**

Anotar no `README.md` do submodule, em "Setup", o comando de run (`python -m uau_extractor.ingestao`).
Depois, na raiz do parent `bi-top-web`:

```bash
git add services/uau-extractor
git commit -m "bump uau-extractor -> fatia 1 (cliente + slice obras)"
```

---

## Self-Review (preenchido pelo autor do plano)

**Cobertura do spec:**
- Cliente + lifecycle de token (B) → Tasks 3–7. ✅
- `_ensure_auth` proativo + retry 401 reativo → Tasks 5, 6. ✅
- Encanamento de ingestão (extract→transform→upsert+log) → Tasks 12, 13. ✅
- Schema `uau` PK de auditoria → Task 11. ✅
- Config (empresa/obra/margem) → Task 1. ✅
- Testes (token via MockTransport+clock, transform via fixture) → Tasks 3–7, 12. ✅
- Run live manual → Task 14. ✅
- Descoberta do endpoint/colunas (unknown externo) → Task 10 (portão da Fase B). ✅

**Placeholders:** Fase A 100% concreta. Fase B tem mapeamentos de exemplo explicitamente
marcados "AJUSTAR ao fixture" — é dependência externa real (resposta da API), resolvida pela
Task 10 antes das Tasks 11–13, não preguiça de plano.

**Consistência de tipos:** `UauClient(now=, sleep=, transport=)`, `post(endpoint, payload)`,
`db.get_engine(db_url)`, `db.upsert_dataframe(engine, df, tabela, pk_cols)`,
`transformar(registros)->DataFrame`, `consultar(client, empresa, obra)->list[dict]` — nomes
batem entre tasks. ✅
