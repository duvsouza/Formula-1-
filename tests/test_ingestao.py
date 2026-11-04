"""Testes de pipeline/ingestao.py (critérios de aceite da docstring)."""

import duckdb
import pytest

from pipeline import ingestao


@pytest.fixture
def pasta_raw(tmp_path, monkeypatch):
    """Pasta raw/ temporária com os 14 CSVs, duas linhas cada."""
    pasta = tmp_path / "raw"
    pasta.mkdir()
    for arquivo in ingestao.ARQUIVO_PARA_TABELA:
        (pasta / arquivo).write_text(
            "id,nome,valor\n1,Pérez,\\N\n2,Räikkönen,NA\n", encoding="utf-8"
        )
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta)
    return pasta


def test_ler_csv_nao_converte_nada(tmp_path):
    arquivo = tmp_path / "x.csv"
    arquivo.write_text(
        "num,texto\n007,\\N\n1.50,NA\n,NULL\n2,São Paulo\n", encoding="utf-8"
    )

    df = ingestao.ler_csv(arquivo)

    assert list(df["num"][:2]) == ["007", "1.50"]  # sem virar número
    assert list(df["texto"]) == ["\\N", "NA", "NULL", "São Paulo"]
    assert df["num"].isna().tolist() == [False, False, True, False]  # vazio -> nulo


@pytest.mark.parametrize(
    ("n", "esperado"),
    [(0, "0"), (999, "999"), (1000, "1.000"), (701433, "701.433")],
)
def test_formatar_usa_ponto_no_milhar(n, esperado):
    assert ingestao.formatar(n) == esperado


def test_main_para_antes_de_gravar_se_faltar_csv(pasta_raw, banco, capsys):
    (pasta_raw / "lap_times.csv").unlink()

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    assert saida.value.code == 1
    assert "lap_times.csv" in capsys.readouterr().err
    assert not banco.exists()


def test_main_grava_14_tabelas_varchar_e_e_idempotente(pasta_raw, banco, capsys):
    ingestao.main()
    primeira = capsys.readouterr().out
    ingestao.main()
    segunda = capsys.readouterr().out

    linhas = primeira.strip().splitlines()
    assert len(linhas) == 15
    assert linhas[-1].split() == ["total", "28"]
    assert primeira == segunda

    with duckdb.connect(str(banco), read_only=True) as con:
        tipos = {r[1] for r in con.execute("DESCRIBE raw.resultados").fetchall()}
        ausentes = con.execute(
            "SELECT count(*) FROM raw.resultados WHERE valor = '\\N'"
        ).fetchall()[0][0]
        nomes = con.execute("SELECT nome FROM raw.pilotos ORDER BY id").fetchall()
    assert tipos == {"VARCHAR"}
    assert ausentes == 1
    assert nomes == [("Pérez",), ("Räikkönen",)]
