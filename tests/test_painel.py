"""Testes de painel.py: formatação, leitura e gráficos."""

import duckdb
import pandas as pd
import plotly.graph_objects as go
import pytest

import painel

# ---------------------------------------------------------------- formato


@pytest.mark.parametrize(
    ("valor", "casas", "esperado"),
    [
        (0, 0, "0"),
        (1125, 0, "1.125"),
        (701433, 0, "701.433"),
        (1234.5, 1, "1.234,5"),
        (-1234.5, 2, "-1.234,50"),
        (0.25, 2, "0,25"),
    ],
)
def test_numero_no_padrao_brasileiro(valor, casas, esperado):
    assert painel.numero(valor, casas) == esperado


@pytest.mark.parametrize(
    ("valor", "casas", "esperado"),
    [(36.5, 1, "36,5%"), (23.46, 1, "23,5%"), (100, 0, "100%")],
)
def test_pct(valor, casas, esperado):
    assert painel.pct(valor, casas) == esperado


# ---------------------------------------------------------------- leitura


def test_ler_sem_banco_avisa_e_nao_cria_arquivo(banco):
    with pytest.raises(painel.DadosFaltando) as erro:
        painel.ler(["kpis", "abandonos"])

    assert erro.value.sem_banco
    assert erro.value.faltando == ["kpis", "abandonos"]
    assert not banco.exists()


def test_ler_lista_os_marts_que_faltam(banco):
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.kpis AS SELECT 1 AS x")

    with pytest.raises(painel.DadosFaltando) as erro:
        painel.ler(["kpis", "abandonos", "ranking_pilotos"])

    assert not erro.value.sem_banco
    assert erro.value.faltando == ["abandonos", "ranking_pilotos"]


def test_ler_devolve_dataframes_e_fecha_a_conexao(banco):
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.kpis AS SELECT 75 AS temporadas")

    dados = painel.ler(["kpis"])

    assert dados["kpis"].to_dict("records") == [{"temporadas": 75}]
    # Se ler() deixasse a conexão read_only aberta, abrir para escrita no
    # mesmo processo falharia.
    duckdb.connect(str(banco)).close()


# ---------------------------------------------------------------- gráficos


def ranking(coluna_rotulo, coluna_valor, n=15):
    """Mart fictício já em ordem decrescente, como sai do ORDER BY."""
    return pd.DataFrame(
        {
            coluna_rotulo: [f"item {i:02d}" for i in range(n)],
            coluna_valor: list(range(n * 10, 0, -10)),
        }
    )


GRAFICOS_RANKING = [
    (painel.grafico_vitorias_pilotos, "piloto", "vitorias", "04 ·"),
    (painel.grafico_vitorias_equipes, "equipe", "vitorias", "05 ·"),
    (
        painel.grafico_vitorias_nacionalidade,
        "nacionalidade",
        "corridas_vencidas",
        "12 ·",
    ),
    (painel.grafico_motivos_abandono, "motivo", "abandonos", "13 ·"),
    (painel.grafico_ganho_posicoes, "piloto", "media_posicoes_ganhas", "11 ·"),
]


@pytest.mark.parametrize(("funcao", "rotulo", "valor", "prefixo"), GRAFICOS_RANKING)
def test_rankings_mostram_top_10_na_ordem_do_mart(funcao, rotulo, valor, prefixo):
    df = ranking(rotulo, valor)

    fig = funcao(df)

    assert isinstance(fig, go.Figure)
    assert fig.layout.title.text.startswith(prefixo)
    assert list(fig.data[0].y) == df[rotulo].head(painel.TOP).tolist()
    assert fig.layout.yaxis.autorange == "reversed"  # primeira linha em cima
    assert fig.layout.separators == ",."


def test_grafico_abandono():
    df = pd.DataFrame({"ano": [1950, 1951], "pct_abandono": [40.0, 35.5]})

    fig = painel.grafico_abandono(df)

    assert fig.layout.title.text.startswith("08 ·")
    assert list(fig.data[0].x) == [1950, 1951]
    assert fig.layout.yaxis.ticksuffix == "%"


def test_grafico_pole_mantem_decadas_em_ordem_cronologica():
    df = pd.DataFrame({"decada": [1950, 1960, 1970], "pct_pole_venceu": [40, 45, 38]})

    fig = painel.grafico_pole(df)

    assert fig.layout.title.text.startswith("07 ·")
    assert list(fig.data[0].x) == [1950, 1960, 1970]
    assert fig.layout.xaxis.type == "category"
