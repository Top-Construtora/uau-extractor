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
