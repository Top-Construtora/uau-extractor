# tests/test_client_token.py
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


def test_reusa_token_dentro_do_ttl():
    api = FakeApi()
    c = build(api, Clock(1000.0))
    c.post("Obra/Consultar", {})
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 1
    assert api.user_calls == 1
    assert api.data_calls == 2
    c.close()


def test_renova_gateway_apos_expirar():
    api = FakeApi()
    clock = Clock(1000.0)
    c = build(api, clock)
    c.post("Obra/Consultar", {})        # gateway_exp = 1000 + 86400 - 60
    clock.t = 1000.0 + 86400            # passou da expiração (margem 60s)
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 2
    assert api.user_calls == 2
    c.close()


def test_retry_apos_401_reautentica():
    api = FakeApi()
    api.data_responses = [(401, {"msg": "expirado"})]
    c = build(api)
    r = c.post("Obra/Consultar", {})
    assert r.status_code == 200
    assert api.gateway_calls == 2
    assert api.user_calls == 2
    assert api.data_calls == 2
    c.close()


def test_401_persistente_levanta():
    api = FakeApi()
    api.data_responses = [(401, {}), (401, {})]
    c = build(api)
    with pytest.raises(UauAuthError):
        c.post("Obra/Consultar", {})
    c.close()


def test_retry_em_500():
    api = FakeApi()
    api.data_responses = [(500, {"erro": "instável"}), (200, [{"ok": 1}])]
    c = build(api)
    r = c.post("Obra/Consultar", {})
    assert r.status_code == 200
    assert api.gateway_calls == 1
    assert api.user_calls == 1
    assert api.data_calls == 2
    c.close()


def test_borda_da_margem_de_expiracao():
    api = FakeApi()
    clock = Clock(1000.0)
    c = build(api, clock)
    c.post("Obra/Consultar", {})   # gateway_exp = 1000 + 86400 - 60 = 87340
    clock.t = 87339.0              # 1s antes da expiração -> NÃO renova
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 1
    clock.t = 87340.0             # exatamente na expiração -> renova
    c.post("Obra/Consultar", {})
    assert api.gateway_calls == 2
    c.close()
