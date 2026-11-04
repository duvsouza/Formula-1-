"""Critérios de aceite das specs, conferidos no f1.duckdb real.

Só leem o banco (read_only). São pulados se o pipeline ainda não rodou.
Rodar só estes:  uv run pytest -m integracao
Pular estes:     uv run pytest -m "not integracao"
"""

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from conftest import BANCO_REAL, RAIZ

from pipeline.transformacao import COLUNAS

pytestmark = pytest.mark.integracao

ARQUIVOS_SQL = sorted((RAIZ / "sql" / "marts").glob("*.sql"))


@pytest.fixture(scope="module")
def con():
    if not BANCO_REAL.is_file():
        pytest.skip("f1.duckdb não existe; rode o pipeline antes")
    try:
        conexao = duckdb.connect(str(BANCO_REAL), read_only=True)
    except duckdb.IOException as e:
        pytest.skip(f"f1.duckdb em uso por outro processo: {e}")
    yield conexao
    conexao.close()


def um(con, sql):
    return con.execute(sql).fetchall()[0][0]


# ---------------------------------------------------------------- refined
CONTAGENS_REFINED = {
    "circuitos": 77,
    "equipes": 212,
    "pilotos": 861,
    "temporadas": 75,
    "corridas": 1125,
    "status_final": 139,
    "resultados": 26759,
    "resultados_sprint": 360,
    "resultados_equipes": 12625,
    "classificacao_pilotos": 34863,
    "classificacao_equipes": 13391,
    "classificatorio": 10494,
    "voltas": 589081,
    "pit_stops": 11371,
}


def test_refined_tem_as_14_tabelas():
    assert set(CONTAGENS_REFINED) == set(COLUNAS)


@pytest.mark.parametrize(("tabela", "linhas"), CONTAGENS_REFINED.items())
def test_refined_contagens(con, tabela, linhas):
    assert um(con, f"SELECT count(*) FROM refined.{tabela}") == linhas


@pytest.mark.parametrize(
    ("sql", "esperado"),
    [
        ("SELECT count(*) FROM refined.resultados WHERE posicao IS NULL", 10953),
        ("SELECT count(*) FROM refined.resultados WHERE tempo_ms IS NULL", 19079),
        ("SELECT count(*) FROM refined.classificatorio WHERE q2_ms IS NULL", 4647),
        ("SELECT count(*) FROM refined.classificatorio WHERE q3_ms IS NULL", 6865),
        ("SELECT count(*) FROM refined.resultados WHERE largada = 0", 1638),
        ("SELECT sum(pontos) FROM refined.resultados", Decimal("53187.05")),
        ("SELECT max(pontos) FROM refined.classificacao_pilotos", Decimal("575.00")),
        ("SELECT min(data)::VARCHAR FROM refined.corridas", "1950-05-13"),
        ("SELECT max(data)::VARCHAR FROM refined.corridas", "2024-12-08"),
        ("SELECT min(data_nascimento)::VARCHAR FROM refined.pilotos", "1896-12-28"),
        ("SELECT max(data_nascimento)::VARCHAR FROM refined.pilotos", "2005-05-08"),
    ],
)
def test_refined_criterios_da_spec(con, sql, esperado):
    assert um(con, sql) == esperado


def test_refined_nenhum_varchar_contem_barra_n(con):
    colunas = con.execute(
        "SELECT table_name, column_name FROM duckdb_columns() "
        "WHERE schema_name = 'refined' AND data_type = 'VARCHAR'"
    ).fetchall()
    for tabela, coluna in colunas:
        n = um(con, f"SELECT count(*) FROM refined.{tabela} WHERE {coluna} = '\\N'")
        assert n == 0, f"{tabela}.{coluna}"


def texto_para_ms(coluna: str) -> str:
    """SQL que converte 'SS.mmm', 'M:SS.mmm' ou 'H:MM:SS.mmm' em ms.

    Há voltas de mais de uma hora (corridas interrompidas), então não dá
    para supor sempre M:SS.mmm.
    """
    partes = f"string_split({coluna}, ':')"
    return (
        f"round(list_reduce(list_transform({partes},"
        " lambda p: CAST(p AS DECIMAL(9,3))),"
        " lambda acc, p: acc * 60 + p) * 1000)"
    )


@pytest.mark.parametrize(
    ("tabela", "ms", "texto"),
    [
        ("voltas", "tempo_ms", "tempo_texto"),
        ("pit_stops", "duracao_ms", "duracao_texto"),
    ],
)
def test_refined_ms_bate_com_o_texto(con, tabela, ms, texto):
    divergencias = um(
        con,
        f"SELECT count(*) FROM refined.{tabela} WHERE {ms} <> {texto_para_ms(texto)}",
    )
    assert divergencias == 0


# ---------------------------------------------------------------- marts


@pytest.mark.parametrize("arquivo", ARQUIVOS_SQL, ids=lambda a: a.name)
def test_sql_comeca_com_comentario_da_pergunta(arquivo: Path):
    assert arquivo.read_text(encoding="utf-8").startswith("-- ")


@pytest.mark.parametrize("arquivo", ARQUIVOS_SQL, ids=lambda a: a.name)
def test_sql_roda_sobre_refined_e_nao_volta_vazio(con, arquivo: Path):
    sql = arquivo.read_text(encoding="utf-8").rstrip().removesuffix(";")
    assert um(con, f"SELECT count(*) FROM ({sql})") > 0


def test_marts_existem_um_por_arquivo(con):
    tabelas = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'marts'"
        ).fetchall()
    }
    assert tabelas == {a.stem[3:] for a in ARQUIVOS_SQL}


def test_kpis(con):
    temporadas, corridas, circuitos = con.execute(
        "SELECT temporadas, corridas, circuitos FROM marts.kpis"
    ).fetchall()[0]
    assert (temporadas, corridas, circuitos) == (75, 1125, 77)


def test_kpis_pct_abandono_entre_min_e_max_das_temporadas(con):
    assert um(
        con,
        """
        SELECT k.pct_abandono BETWEEN min(a.pct_abandono) AND max(a.pct_abandono)
        FROM marts.kpis AS k, marts.abandonos AS a
        GROUP BY k.pct_abandono
        """,
    )


@pytest.mark.parametrize(
    ("ano", "piloto", "pontos"),
    [(2024, "Max Verstappen", Decimal("437")), (1950, "Nino Farina", Decimal("30"))],
)
def test_campeoes_pilotos(con, ano, piloto, pontos):
    assert um(con, "SELECT count(*) FROM marts.campeoes_pilotos") == 75
    assert con.execute(
        "SELECT piloto, pontos FROM marts.campeoes_pilotos WHERE ano = ?", [ano]
    ).fetchall() == [(piloto, pontos)]


@pytest.mark.parametrize(("ano", "equipe"), [(2024, "McLaren"), (1958, "Vanwall")])
def test_campeoes_equipes(con, ano, equipe):
    assert um(con, "SELECT count(*) FROM marts.campeoes_equipes") == 67
    assert con.execute(
        "SELECT equipe FROM marts.campeoes_equipes WHERE ano = ?", [ano]
    ).fetchall() == [(equipe,)]


@pytest.mark.parametrize(
    ("piloto", "vitorias", "titulos"),
    [
        ("Lewis Hamilton", 105, 7),
        ("Michael Schumacher", 91, 7),
        ("Ralf Schumacher", 6, 0),
    ],
)
def test_ranking_pilotos(con, piloto, vitorias, titulos):
    assert con.execute(
        "SELECT vitorias, titulos FROM marts.ranking_pilotos WHERE piloto = ?",
        [piloto],
    ).fetchall() == [(vitorias, titulos)]
