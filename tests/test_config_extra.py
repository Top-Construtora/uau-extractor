# tests/test_config_extra.py
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
