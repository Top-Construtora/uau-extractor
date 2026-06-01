"""Acesso ao Postgres (Supabase): engine + upsert idempotente no schema `uau`.

Espelha o padrão de lib/sienge-bi-shared (search_path, batch p/ pooler PgBouncer),
adaptado para o schema `uau`.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Iterator, Sequence

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

    Retorna {"lidas": N, "afetadas": M}. Verificado contra Postgres no run manual.
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
