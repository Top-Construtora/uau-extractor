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
        if not (200 <= r.status_code < 300):  # Trinus devolve 201 no /oauth/access-token
            raise UauAuthError(f"auth do gateway falhou: {r.status_code}")
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
        if not (200 <= r.status_code < 300):
            raise UauAuthError(f"auth de usuário falhou: {r.status_code}")
        self._user_token = _extrair_token_usuario(r.json())

    def _ensure_auth(self) -> None:
        if self._gateway_token is None or self._now() >= self._gateway_exp:
            self._auth_gateway()
            self._user_token = None  # gateway novo -> usuário também renova
        # O TTL do token de usuário não é documentado e não é rastreado:
        # ele é renovado reativamente no 401 (custa 1 round-trip por expiração).
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
        if isinstance(ultimo, BaseException):
            raise ultimo
        raise UauAuthError("falha sem resposta nem exceção registrada")  # defensivo

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
                raise UauAuthError(f"401/403 após re-autenticação: {r.status_code}")
        r.raise_for_status()
        return r

    def post(self, endpoint: str, payload: dict) -> httpx.Response:
        return self.request("POST", endpoint, json=payload)

    def close(self) -> None:
        self._http.close()
