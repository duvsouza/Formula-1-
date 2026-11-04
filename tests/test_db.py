"""Testes de pipeline/db.py (critérios de aceite D1-D4)."""

import pandas as pd

from pipeline import db


def test_conectar_cria_banco_no_caminho_do_projeto_e_nao_na_pasta_corrente(
    banco, tmp_path, monkeypatch
):
    outra_pasta = tmp_path / "outra"
    outra_pasta.mkdir()
    monkeypatch.chdir(outra_pasta)

    db.conectar().close()

    assert banco.is_file()
    assert not (outra_pasta / "f1.duckdb").exists()


def test_criar_schema_e_idempotente(con):
    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")

    schemas = con.execute(
        "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = 'raw'"
    ).fetchall()[0][0]
    assert schemas == 1


def test_gravar_devolve_contagem_do_banco_e_e_idempotente(con):
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["1", "2", "3"]})

    assert db.gravar(con, df, "raw", "t") == 3
    assert db.gravar(con, df, "raw", "t") == 3


def test_gravar_mantem_texto_e_nulo_sem_converter(con):
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["\\N", None, "Pérez"]}, dtype=str)

    db.gravar(con, df, "raw", "t")

    tipo = con.execute("DESCRIBE raw.t").fetchall()[0][1]
    valores = con.execute("SELECT a FROM raw.t ORDER BY rowid").fetchall()
    assert tipo == "VARCHAR"
    assert valores == [("\\N",), (None,), ("Pérez",)]


def test_gravar_nao_deixa_view_para_tras(con):
    db.criar_schema(con, "raw")

    db.gravar(con, pd.DataFrame({"a": [1]}), "raw", "t")

    views = con.execute(
        "SELECT count(*) FROM duckdb_views() WHERE NOT internal"
    ).fetchall()[0][0]
    assert views == 0
