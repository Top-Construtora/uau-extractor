"""Cliente HTTP da API UAU/Trinus.

Fluxo de autenticação em 3 camadas (ver docs/"Manual de Integração e Autenticação UAU.pdf"):

1. Token de integração (estático): fornecido pela Globaltec após cadastro de desenvolvedor
   em https://clientes.uau.com.br/. Vai no header `X-Integration-Authorization`.

2. Token do API Gateway Trinus (OAuth2 client_credentials, validade 24h):
       POST {gateway_url}/oauth/access-token
       Header: Authorization: Basic {trinus_basic}      # base64(client_id:secret_id)
       Body:   {"grant_type": "client_credentials"}
       Retorno: {"access_token", "token_type", "expires_in": 86400}

3. Token de usuário UAU:
       POST {api_base_url}/Autenticador/AutenticarUsuario
       Headers: client_id, access_token (passo 2), X-Integration-Authorization, Content-Type
       Body:    {"login": <login>, "Senha": <senha>}
       Retorno: token de usuário -> header `Authorization` nas chamadas de dados.

Chamadas de dados (ex.: POST {api_base_url}/Anexo/ConsultarChavesComentario) usam todos os
headers acima + `Authorization: {token_usuario}`.

Catálogo de endpoints: ver docs/links.md (Swagger UAUApi + ajuda Globaltec).

STATUS: esqueleto de setup — auth e chamadas serão implementadas na próxima fase.
"""
from __future__ import annotations

import httpx

from .config import Settings


class UauClient:
    def __init__(self, settings: Settings, timeout: float = 30.0) -> None:
        self.settings = settings
        self._http = httpx.Client(timeout=timeout)
        self._access_token: str | None = None  # token do gateway (passo 2)
        self._user_token: str | None = None  # token de usuário UAU (passo 3)

    def _obter_token_gateway(self) -> str:
        """Passo 2 — OAuth2 client_credentials no API Gateway Trinus. TODO (próxima fase)."""
        raise NotImplementedError

    def _obter_token_usuario(self) -> str:
        """Passo 3 — autentica o usuário UAU e devolve o token de usuário. TODO (próxima fase)."""
        raise NotImplementedError

    def autenticar(self) -> None:
        """Orquestra os passos 2 e 3, populando os tokens. TODO (próxima fase)."""
        raise NotImplementedError

    def post(self, endpoint: str, payload: dict) -> httpx.Response:
        """Chamada genérica de dados na UAUAPi com todos os headers. TODO (próxima fase)."""
        raise NotImplementedError

    def close(self) -> None:
        self._http.close()
