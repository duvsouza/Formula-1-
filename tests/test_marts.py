"""Testes de pipeline/marts.py (seção 4 da spec: erros e transação)."""

import duckdb
import pytest

from pipeline import marts
from pipeline.db import conectar


@pytest.fixture
def pasta_sql(tmp_path, monkeypatch):
    """sql/marts/ temporária; _RAIZ aponta para tmp_path."""
    pasta = tmp_path / "sql" / "marts"
    pasta.mkdir(parents=True)
    monkeypatch.setattr(marts, "_RAIZ", tmp_path)
    monkeypatch.setattr(marts, "PASTA_SQL", pasta)
    return pasta


@pytest.fixture
def refined(banco):
    """f1.duckdb temporário com as 14 tabelas de refined (uma linha cada)."""
    con = conectar()
    con.execute("CREATE SCHEMA refined")
    for tabela in marts.TABELAS_REFINED:
        con.execute(f"CREATE TABLE refined.{tabela} AS SELECT 1 AS x")
    con.close()
    return banco


def escrever(pasta, nome, sql):
    arquivo = pasta / nome
    arquivo.write_text(sql, encoding="utf-8")
    return arquivo


def tabelas_marts(banco):
    with duckdb.connect(str(banco), read_only=True) as con:
        return {
            r[0]: con.execute(f"SELECT * FROM marts.{r[0]}").fetchall()
            for r in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'marts'"
            ).fetchall()
        }


# ---------------------------------------------------------------- nomes


def test_validar_nomes_tira_o_prefixo(pasta_sql):
    a = escrever(pasta_sql, "01_kpis.sql", "SELECT 1")
    b = escrever(pasta_sql, "12_por_nacionalidade.sql", "SELECT 1")

    assert marts._validar_nomes([a, b]) == [(a, "kpis"), (b, "por_nacionalidade")]


@pytest.mark.parametrize("nome", ["kpis.sql", "1_kpis.sql", "001_kpis.sql"])
def test_validar_nomes_recusa_arquivo_sem_prefixo(pasta_sql, capsys, nome):
    arquivo = escrever(pasta_sql, nome, "SELECT 1")

    with pytest.raises(SystemExit):
        marts._validar_nomes([arquivo])

    assert nome in capsys.readouterr().err


def test_validar_nomes_recusa_mesma_tabela_ignorando_maiusculas(pasta_sql, capsys):
    a = escrever(pasta_sql, "01_Kpis.sql", "SELECT 1")
    b = escrever(pasta_sql, "02_kpis.sql", "SELECT 1")

    with pytest.raises(SystemExit):
        marts._validar_nomes([a, b])

    erro = capsys.readouterr().err
    assert "01_Kpis.sql" in erro
    assert "02_kpis.sql" in erro


# ---------------------------------------------------------------- _criar_mart


def test_criar_mart_tira_ponto_e_virgula_e_conta_linhas(con, pasta_sql):
    con.execute("CREATE SCHEMA marts")
    arquivo = escrever(pasta_sql, "01_a.sql", "SELECT * FROM range(3) t(x);\n\n")

    assert marts._criar_mart(con, arquivo, "a") == 3


def test_criar_mart_vazio_falha(con, pasta_sql):
    con.execute("CREATE SCHEMA marts")
    arquivo = escrever(pasta_sql, "01_a.sql", "SELECT 1 AS x WHERE false")

    with pytest.raises(marts.FalhaEtapa, match="0 linhas"):
        marts._criar_mart(con, arquivo, "a")


def test_criar_mart_com_sql_quebrada_diz_o_arquivo(con, pasta_sql):
    con.execute("CREATE SCHEMA marts")
    arquivo = escrever(pasta_sql, "01_a.sql", "SELEC 1")

    with pytest.raises(marts.FalhaEtapa, match="sql/marts/01_a.sql"):
        marts._criar_mart(con, arquivo, "a")


# ---------------------------------------------------------------- main


def test_main_sem_refined_manda_rodar_a_transformacao(banco, pasta_sql, capsys):
    with pytest.raises(SystemExit):
        marts.main()

    assert "pipeline.transformacao" in capsys.readouterr().err


def test_main_sem_arquivos_sql_para(refined, pasta_sql, capsys):
    with pytest.raises(SystemExit):
        marts.main()

    assert "Nenhum arquivo .sql" in capsys.readouterr().err


def test_main_cria_um_mart_por_arquivo_e_e_idempotente(refined, pasta_sql, capsys):
    escrever(pasta_sql, "02_b.sql", "SELECT * FROM range(1500)")
    escrever(pasta_sql, "01_a.sql", "SELECT x FROM refined.corridas;")

    marts.main()
    primeira = capsys.readouterr().out
    marts.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert primeira.splitlines() == [
        "✓ marts.a      1 linha",
        "✓ marts.b  1.500 linhas",
        "2 marts, 1.501 linhas",
    ]


def test_main_apaga_mart_cujo_arquivo_sumiu(refined, pasta_sql):
    escrever(pasta_sql, "01_a.sql", "SELECT 1 AS x")
    velho = escrever(pasta_sql, "02_b.sql", "SELECT 2 AS x")
    marts.main()

    velho.unlink()
    marts.main()

    assert set(tabelas_marts(refined)) == {"a"}


def test_main_com_falha_mantem_marts_da_ultima_execucao(refined, pasta_sql, capsys):
    escrever(pasta_sql, "01_a.sql", "SELECT 1 AS x")
    marts.main()
    antes = tabelas_marts(refined)

    escrever(pasta_sql, "01_a.sql", "SELECT 99 AS x")
    escrever(pasta_sql, "02_b.sql", "SELEC quebrado")
    with pytest.raises(SystemExit):
        marts.main()

    assert "02_b.sql" in capsys.readouterr().err
    assert tabelas_marts(refined) == antes == {"a": [(1,)]}
