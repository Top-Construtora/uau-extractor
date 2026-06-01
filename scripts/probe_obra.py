"""Probe de descoberta: autentica e chama Obras/ConsultarObraPorChave, salvando a resposta.

Uso (com .env preenchido — requer UAU_TOKEN_INTEGRACAO, UAU_EMPRESA, UAU_OBRA):
    python scripts/probe_obra.py

Endpoint confirmado no Swagger (UAUApi 1.0/swagger):
    POST {UAU_API_BASE_URL}/Obras/ConsultarObraPorChave
    body:    {"empresa": <int>, "obra": "<str>"}
    retorno: modelo Obra (Cod_obr, Empresa_obr, Descr_obr, Status_obr, Ender_obr,
             Fone_obr, Fisc_obr, DtIni_obr, Dtfim_obr, TipoObra_obr, EnderEntr_obr,
             CEI_obr, DataCad_obr, DataAlt_obr, UsrCad_obr).

A resposta salva vira a fixture de teste do transform e fixa as colunas de uau.fato_obra.
"""
import json
import os
from pathlib import Path

from uau_extractor.client import UauClient
from uau_extractor.config import carregar

DESTINO = Path("tests/fixtures/obra_sample.json")


def main() -> None:
    cfg = carregar()
    endpoint = os.environ.get("UAU_ENDPOINT_OBRA", "Obras/ConsultarObraPorChave")
    payload = {"empresa": int(cfg.empresa), "obra": cfg.obra}
    c = UauClient(cfg)
    try:
        resp = c.post(endpoint, payload)
        dados = resp.json()
    finally:
        c.close()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(dados) if isinstance(dados, list) else 1
    print(f"OK — {n} registro(s) salvos em {DESTINO}")


if __name__ == "__main__":
    main()
