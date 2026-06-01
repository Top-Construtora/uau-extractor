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
            return httpx.Response(201, json={  # Trinus devolve 201 Created
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
