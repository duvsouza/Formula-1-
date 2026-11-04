"""Testes de pipeline/transformacao.py (seções 3 a 6 da spec)."""

from datetime import date, time
from decimal import Decimal

import duckdb
import pytest
from conftest import criar_raw_vazio

from pipeline import transformacao as tr
from pipeline.db import conectar


def avaliar(con, tipo: str, texto: str):
    """Devolve (está no formato?, valor convertido ou None)."""
    formato_ok, conversao = tr.CONVERSOES[tipo]
    literal = f"'{texto}'"
    ok = con.execute(f"SELECT {formato_ok.format(v=literal)}").fetchall()[0][0]
    if not ok:
        return False, None
    return True, con.execute(f"SELECT {conversao.format(v=literal)}").fetchall()[0][0]


@pytest.mark.parametrize(
    ("tipo", "texto", "esperado"),
    [
        ("inteiro", "42", 42),
        ("inteiro", "-3", -3),
        ("pontos", "0.5", Decimal("0.50")),
        ("pontos", "1.33", Decimal("1.33")),
        ("pontos", "25", Decimal("25.00")),
        ("double", "52.0786", 52.0786),
        ("data", "2024-12-08", date(2024, 12, 8)),
        ("hora", "14:00:00", time(14, 0)),
        ("tempo_ms", "1:23.456", 83_456),
        ("tempo_ms", "0:59.001", 59_001),
        ("texto", "+5.478", "+5.478"),
    ],
)
def test_conversao_valida(con, tipo, texto, esperado):
    assert avaliar(con, tipo, texto) == (True, esperado)


@pytest.mark.parametrize(
    ("tipo", "texto"),
    [
        ("inteiro", "1.7"),  # o cast arredondaria para 2 em silêncio
        ("inteiro", "abc"),
        ("pontos", "1.333"),  # mais de 2 casas
        ("double", "norte"),
        ("data", "08/12/2024"),
        ("data", "abc"),
        ("hora", "25:00:00"),
        ("tempo_ms", "83.456"),
        ("tempo_ms", "1:60.000"),
        ("tempo_ms", "1:23.45"),
    ],
)
def test_conversao_rejeita_formato_errado(con, tipo, texto):
    assert avaliar(con, tipo, texto) == (False, None)


def test_valor_troca_ausente_por_null(con):
    col = tr.c("x", "x", "texto")
    expr = tr.valor(col)

    resultado = con.execute(
        f"SELECT {expr} FROM (VALUES ('\\N'), ('a')) AS t(x)"
    ).fetchall()

    assert resultado == [(None,), ("a",)]


def test_colunas_e_chaves_cobrem_as_mesmas_14_tabelas():
    assert len(tr.COLUNAS) == 14
    assert set(tr.COLUNAS) == set(tr.CHAVES)
    for tabela, chave in tr.CHAVES.items():
        originais = {col.original for col in tr.COLUNAS[tabela]}
        assert set(chave) <= originais, tabela


def test_todo_tipo_declarado_tem_conversao():
    tipos = {col.tipo for cols in tr.COLUNAS.values() for col in cols}
    assert tipos <= set(tr.CONVERSOES)


def test_nomes_novos_sao_snake_case_e_unicos_por_tabela():
    for tabela, colunas in tr.COLUNAS.items():
        novos = [col.nova for col in colunas]
        assert len(novos) == len(set(novos)), tabela
        assert all(n == n.lower() and " " not in n for n in novos), tabela


# ---------------------------------------------------------------- validar


def criar_resultados_equipes(con, linhas):
    """raw.resultados_equipes com as linhas dadas (tudo texto)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        "CREATE OR REPLACE TABLE raw.resultados_equipes ("
        '"constructorResultsId" VARCHAR, "raceId" VARCHAR, '
        '"constructorId" VARCHAR, "points" VARCHAR, "status" VARCHAR)'
    )
    if linhas:
        con.executemany(
            "INSERT INTO raw.resultados_equipes VALUES (?, ?, ?, ?, ?)", linhas
        )


def test_validar_tabela_limpa(con):
    criar_resultados_equipes(
        con, [("1", "10", "5", "4.5", "\\N"), ("2", "10", "6", "0", "\\N")]
    )

    erros, numeros = tr.validar(con, "resultados_equipes")

    assert erros == []
    assert numeros == {"raw": 2, "ausentes": 2, "duplicatas": 0}


def test_validar_conta_copia_identica_sem_erro(con):
    linha = ("1", "10", "5", "4.5", "\\N")
    criar_resultados_equipes(con, [linha, linha])

    erros, numeros = tr.validar(con, "resultados_equipes")

    assert erros == []
    assert numeros["duplicatas"] == 1


def test_validar_acusa_chave_repetida_com_conteudo_diferente(con):
    criar_resultados_equipes(
        con, [("1", "10", "5", "4.5", "\\N"), ("1", "10", "5", "9", "\\N")]
    )

    erros, _ = tr.validar(con, "resultados_equipes")

    assert len(erros) == 1
    assert "constructorResultsId" in erros[0]


def test_validar_acusa_formato_errado_com_exemplo(con):
    criar_resultados_equipes(con, [("1", "10", "5", "1.333", "\\N")])

    erros, _ = tr.validar(con, "resultados_equipes")

    assert len(erros) == 1
    assert "resultados_equipes.points" in erros[0]
    assert "1.333" in erros[0]


def test_validar_acusa_nulo_em_coluna_obrigatoria(con):
    criar_resultados_equipes(con, [("1", "\\N", "5", "1", "\\N")])

    erros, _ = tr.validar(con, "resultados_equipes")

    assert len(erros) == 1
    assert "resultados_equipes.raceId" in erros[0]
    assert "NOT NULL" in erros[0]


# ---------------------------------------------------------------- transformar


def test_transformar_renomeia_converte_deduplica_e_ordena(con):
    linha = ("2", "10", "6", "0.5", "D")
    criar_resultados_equipes(con, [linha, ("1", "10", "5", "4.5", "\\N"), linha])

    df = tr.transformar(con, "resultados_equipes")

    assert list(df.columns) == [
        "id_resultado_equipe",
        "id_corrida",
        "id_equipe",
        "pontos",
        "status",
    ]
    assert df["id_resultado_equipe"].tolist() == [1, 2]
    assert df["pontos"].tolist() == [Decimal("4.50"), Decimal("0.50")]
    assert df["status"].isna().tolist() == [True, False]


def test_tabelas_faltando_lista_todas_sem_raw(con):
    con.execute("CREATE SCHEMA raw")
    assert tr.tabelas_faltando(con) == list(tr.COLUNAS)


# ---------------------------------------------------------------- main


def test_main_sem_raw_manda_rodar_a_ingestao(banco, capsys):
    with pytest.raises(SystemExit) as saida:
        tr.main()

    assert saida.value.code == 1
    assert "pipeline.ingestao" in capsys.readouterr().err


def test_main_com_valor_invalido_para_sem_gravar_nada(banco, capsys):
    con = conectar()
    criar_raw_vazio(con)
    con.execute(
        "INSERT INTO raw.corridas (raceId, year, round, circuitId, name, date, url) "
        "VALUES ('1', '2024', '1', '1', 'GP', 'abc', 'u')"
    )
    con.close()

    with pytest.raises(SystemExit) as saida:
        tr.main()

    assert saida.value.code == 1
    assert "corridas.date" in capsys.readouterr().err
    with duckdb.connect(str(banco), read_only=True) as con:
        schemas = con.execute(
            "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = 'refined'"
        ).fetchall()[0][0]
    assert schemas == 0


def test_main_grava_refined_com_nomes_e_tipos_da_spec(banco, capsys):
    con = conectar()
    criar_raw_vazio(con)
    con.execute(
        "INSERT INTO raw.corridas (raceId, year, round, circuitId, name, date, "
        "time, url) VALUES ('1', '2024', '1', '1', 'GP', '2024-12-08', '\\N', 'u')"
    )
    con.close()

    tr.main()
    primeira = capsys.readouterr().out
    tr.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert len(primeira.strip().splitlines()) == 16  # cabeçalho + 14 + total
    with duckdb.connect(str(banco), read_only=True) as con:
        tipos = {
            (t, c): tipo
            for t, c, tipo in con.execute(
                "SELECT table_name, column_name, data_type FROM duckdb_columns() "
                "WHERE schema_name = 'refined'"
            ).fetchall()
        }
        corrida = con.execute("SELECT data, hora FROM refined.corridas").fetchall()
    assert tipos[("corridas", "data")] == "DATE"
    assert tipos[("corridas", "hora")] == "TIME"
    assert tipos[("resultados", "pontos")] == "DECIMAL(6,2)"
    assert tipos[("classificatorio", "q1_ms")] == "INTEGER"
    assert tipos[("circuitos", "latitude")] == "DOUBLE"
    assert tipos[("pilotos", "numero_carro")] == "VARCHAR"
    assert corrida == [(date(2024, 12, 8), None)]
    originais = {c.original for cols in tr.COLUNAS.values() for c in cols}
    novas = {c.nova for cols in tr.COLUNAS.values() for c in cols}
    sobreviventes = {c for _, c in tipos} & (originais - novas)
    assert sobreviventes == set()
