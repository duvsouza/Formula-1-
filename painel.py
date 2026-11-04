"""Leitura, formatação e gráficos do painel de Fórmula 1. Não importa streamlit.

A página é app.py, executável com:
    uv run streamlit run app.py

Fonte da verdade: esta spec. O código é consequência dela.

1. LEITURA
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>. Nenhuma outra SQL.
   Conexão com duckdb.connect(f1.duckdb, read_only=True), aberta e fechada
   dentro de ler(). O caminho do f1.duckdb é resolvido a partir da pasta
   deste arquivo, não do diretório corrente.
   Por quê: conexão aberta segura o arquivo, e o pipeline.marts não
   consegue gravar com o painel de pé.

2. NENHUM CÁLCULO
   Proibido aqui e em app.py: agrupar, somar, tirar média, contar, juntar
   tabelas, pivotar, e qualquer conta entre colunas. Permitido: ordenar,
   filtrar linhas, pegar as n primeiras, renomear coluna e formatar texto.
   Por quê: número novo na tela exige um .sql novo em sql/marts. Todo
   cartão sai pronto do mart kpis.

3. MARTS USADOS (nomes reais do schema marts, specs/marts.md)
   kpis               temporadas, corridas, pilotos, equipes, pct_abandono,
                      vencedores
   abandonos          ano, pct_abandono
   ranking_pilotos    piloto, vitorias
   ranking_equipes    equipe, vitorias
   por_nacionalidade  nacionalidade, corridas_vencidas
   pole_vira_vitoria  decada, pct_pole_venceu
   motivos_abandono   motivo, abandonos
   posicoes_ganhas    piloto, media_posicoes_ganhas (50+ corridas
                      classificadas)
   As definições de largada, abandono e vitória estão no comentário do
   topo de cada .sql.

4. LAYOUT (app.py), de cima para baixo, layout="wide"
   Cabeçalho: título à esquerda; filtro de temporadas à direita.
   Faixa 1: seis cartões, cada rótulo com a definição curta.
   Faixa 2, largura inteira: taxa de abandono por temporada.
   Faixa 3, três colunas: pilotos, equipes e nacionalidades com mais
     vitórias (top 10, barras horizontais, maior em cima).
   Faixa 4, três colunas: a pole vence? (barras verticais por década, em
     ordem cronológica); motivos de abandono (top 10, barras horizontais);
     ganho de posições (top 10, pontos).
   Cada gráfico: título com o número do mart (o prefixo NN_ do .sql), uma
   cor só, eixo com unidade.
   Por quê do número do arquivo: leva direto ao .sql que define o número.

5. FORMATO, funções puras, sem streamlit e sem banco
   pct(valor, casas=1)    -> "23,4%"
   numero(valor, casas=0) -> "1.125"
   Milhar com ponto, decimal com vírgula, sempre, também nos eixos e no
   hover dos gráficos (layout.separators). Não usa locale do sistema.
   Por quê: o resultado não pode depender da máquina de quem roda.
   Uma função por gráfico, recebendo o DataFrame do mart e devolvendo a
   figura plotly, que mantém a ordem de linhas do ORDER BY do mart.
   Por quê: um relatório HTML pode reaproveitar as mesmas funções, e a
   ordem é regra de negócio do SQL, não do Python.

6. FILTRO DE TEMPORADAS (app.py)
   select_slider com as temporadas de abandonos, padrão da primeira à
   última. Recorta só as linhas do gráfico de abandono; cartões e rankings
   valem para a história inteira, e a página diz isso.
   Por quê: recortar linha é SELECT; recalcular vitória ou ranking por
   período seria regra de negócio fora do SQL.

7. CACHE E ERRO (app.py)
   Leitura com st.cache_data; o botão "Recarregar dados" limpa o cache.
   Sem f1.duckdb, ou faltando qualquer mart da seção 3: ler() levanta
   DadosFaltando com os nomes; a página mostra st.error com eles e o
   comando "uv run python -m pipeline.marts", e para.
   Por quê: sem o mart o painel mostraria tela vazia ou número errado sem
   avisar.
"""

from collections.abc import Iterable
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

CAMINHO_BANCO = Path(__file__).resolve().parent / "f1.duckdb"
COMANDO_MARTS = "uv run python -m pipeline.marts"

MARTS = (
    "kpis",
    "abandonos",
    "ranking_pilotos",
    "ranking_equipes",
    "por_nacionalidade",
    "pole_vira_vitoria",
    "motivos_abandono",
    "posicoes_ganhas",
)

COR = "#C8102E"
TOP = 10


class DadosFaltando(Exception):
    """f1.duckdb ausente, ou marts que não existem no banco."""

    def __init__(self, faltando: list[str], sem_banco: bool = False):
        """Guarda o que falta para a página explicar o problema.

        Args:
            faltando: nomes dos marts ausentes (todos, se não há banco).
            sem_banco: True quando o próprio f1.duckdb não existe.
        """
        self.faltando = faltando
        self.sem_banco = sem_banco
        super().__init__(", ".join(faltando))


# ---------------------------------------------------------------- leitura


def ler(marts: Iterable[str] = MARTS) -> dict[str, pd.DataFrame]:
    """Lê cada mart com SELECT * numa conexão somente leitura.

    A conexão é aberta e fechada aqui dentro, para não segurar o arquivo
    enquanto o pipeline tenta gravar.

    Args:
        marts: nomes das tabelas do schema marts a ler.

    Returns:
        Dicionário nome do mart -> DataFrame, na ordem do ORDER BY do .sql.

    Raises:
        DadosFaltando: se o f1.duckdb não existir ou faltar algum mart.
    """
    marts = list(marts)
    # Checa antes de conectar: o erro do connect() read_only num arquivo
    # inexistente não diz que falta rodar o pipeline.
    if not CAMINHO_BANCO.exists():
        raise DadosFaltando(marts, sem_banco=True)

    dados, faltando = {}, []
    con = duckdb.connect(str(CAMINHO_BANCO), read_only=True)
    try:
        for nome in marts:
            try:
                dados[nome] = con.execute(f"SELECT * FROM marts.{nome}").df()
            except duckdb.CatalogException:
                faltando.append(nome)
    finally:
        con.close()

    if faltando:
        raise DadosFaltando(faltando)
    return dados


# ---------------------------------------------------------------- formato


def numero(valor: float, casas: int = 0) -> str:
    """Formata um número no padrão brasileiro, sem depender do locale.

    Args:
        valor: número a formatar.
        casas: casas decimais.

    Returns:
        Texto com milhar em ponto e decimal em vírgula, ex.: "1.125" ou
        "1.234,5".
    """
    # Formata no padrão americano e troca os separadores: não depende do
    # locale da máquina.
    return f"{valor:,.{casas}f}".translate(str.maketrans(",.", ".,"))


def pct(valor: float, casas: int = 1) -> str:
    """Formata um percentual já em escala 0-100, ex.: 23.45 -> "23,5%".

    Args:
        valor: percentual (não fração).
        casas: casas decimais.

    Returns:
        Texto no padrão brasileiro seguido de "%".
    """
    return f"{numero(valor, casas)}%"


# ---------------------------------------------------------------- gráficos


def _estilo(fig: go.Figure, titulo: str) -> go.Figure:
    fig.update_traces(marker_color=COR)
    fig.update_layout(
        title=titulo,
        separators=",.",  # decimal com vírgula, milhar com ponto
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        showlegend=False,
    )
    return fig


def _barras_horizontais(
    df: pd.DataFrame, rotulo: str, valor: str, titulo: str, eixo: str, nome: str
) -> go.Figure:
    # head(TOP) pega as primeiras linhas do ORDER BY do mart; o eixo
    # invertido põe a primeira linha em cima sem reordenar no Python.
    fig = px.bar(
        df.head(TOP),
        x=valor,
        y=rotulo,
        orientation="h",
        labels={valor: eixo, rotulo: nome},
    )
    fig.update_yaxes(autorange="reversed", type="category")
    # Sem o "," o plotly não agrupa milhar e o separators não tem efeito:
    # 1886 sairia "1886" em vez de "1.886".
    fig.update_xaxes(tickformat=",d", hoverformat=",d")
    return _estilo(fig, titulo)


def grafico_abandono(df: pd.DataFrame) -> go.Figure:
    """Linha da taxa de abandono por temporada (mart abandonos).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    fig = px.line(
        df,
        x="ano",
        y="pct_abandono",
        markers=True,
        labels={"ano": "Temporada", "pct_abandono": "Abandono (% das largadas)"},
    )
    fig.update_traces(line_color=COR)
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    return _estilo(fig, "08 · Abandono por temporada")


def grafico_vitorias_pilotos(df: pd.DataFrame) -> go.Figure:
    """Top 10 pilotos por vitórias (mart ranking_pilotos).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    return _barras_horizontais(
        df,
        "piloto",
        "vitorias",
        "04 · Pilotos com mais vitórias",
        "Vitórias (corridas)",
        "Piloto",
    )


def grafico_vitorias_equipes(df: pd.DataFrame) -> go.Figure:
    """Top 10 equipes por vitórias (mart ranking_equipes).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    return _barras_horizontais(
        df,
        "equipe",
        "vitorias",
        "05 · Equipes com mais vitórias",
        "Vitórias (corridas)",
        "Equipe",
    )


def grafico_vitorias_nacionalidade(df: pd.DataFrame) -> go.Figure:
    """Top 10 nacionalidades por vitórias (mart por_nacionalidade).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    return _barras_horizontais(
        df,
        "nacionalidade",
        "corridas_vencidas",
        "12 · Vitórias por nacionalidade",
        "Vitórias (corridas)",
        "Nacionalidade",
    )


def grafico_pole(df: pd.DataFrame) -> go.Figure:
    """Barras do % de corridas vencidas pelo pole, por década.

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    fig = px.bar(
        df,
        x="decada",
        y="pct_pole_venceu",
        labels={"decada": "Década", "pct_pole_venceu": "Pole venceu (% das corridas)"},
    )
    # Categoria na ordem das linhas (ORDER BY decada): cronológica, sem o
    # eixo numérico espaçar as barras de 10 em 10.
    fig.update_xaxes(type="category")
    fig.update_yaxes(ticksuffix="%")
    return _estilo(fig, "07 · A pole vence?")


def grafico_motivos_abandono(df: pd.DataFrame) -> go.Figure:
    """Top 10 motivos de abandono (mart motivos_abandono).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    return _barras_horizontais(
        df,
        "motivo",
        "abandonos",
        "13 · Motivos de abandono",
        "Abandonos (largadas)",
        "Motivo",
    )


def grafico_ganho_posicoes(df: pd.DataFrame) -> go.Figure:
    """Top 10 em ganho médio de posições (mart posicoes_ganhas).

    Args:
        df: DataFrame do mart, na ordem do ORDER BY do .sql.

    Returns:
        Figura plotly pronta para exibir.
    """
    fig = px.scatter(
        df.head(TOP),
        x="media_posicoes_ganhas",
        y="piloto",
        labels={
            "media_posicoes_ganhas": "Ganho médio (posições por corrida)",
            "piloto": "Piloto",
        },
    )
    fig.update_traces(marker_size=11)
    fig.update_yaxes(autorange="reversed", type="category")
    return _estilo(fig, "11 · Ganho de posições")
