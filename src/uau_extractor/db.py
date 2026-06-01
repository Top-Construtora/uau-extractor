"""Acesso ao Postgres (Supabase): engine + upsert idempotente no schema `uau`.

Espelha o padrão de lib/sienge-bi-shared (search_path, batch p/ pooler PgBouncer),
adaptado para o schema `uau`. Implementação real do upsert virá na próxima fase.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
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


def upsert_dataframe(df, tabela: str, pk_cols: list[str], batch_size: int = 200) -> dict:
    """Upsert idempotente de um DataFrame em uau.<tabela>. TODO (próxima fase)."""
    raise NotImplementedError
