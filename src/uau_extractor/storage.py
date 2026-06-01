"""Snapshot opcional do JSON bruto da API UAU no Supabase Storage (bucket uau-raw).

Requer o extra `storage` (pacote supabase). Implementação real na próxima fase.
"""
from __future__ import annotations


def snapshot_json(payload: bytes, caminho: str, bucket: str = "uau-raw") -> str:
    """Sobe o JSON bruto pro Storage e devolve o caminho. TODO (próxima fase)."""
    raise NotImplementedError
