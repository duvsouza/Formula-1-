"""Página do painel de Fórmula 1. Spec: docstring de painel.py.

Execução:
    uv run streamlit run app.py
"""

import streamlit as st

import painel

st.set_page_config(page_title="Fórmula 1 · 75 anos", layout="wide")


@st.cache_data(show_spinner="Lendo marts...")
def carregar():
    """Lê os marts usados pelo painel, guardando o resultado em cache.

    Returns:
        Dicionário nome do mart -> DataFrame, como devolvido por painel.ler.

    Raises:
        painel.DadosFaltando: se o f1.duckdb ou algum mart não existir.
    """
    # Exceção não entra no cache: depois de rodar o pipeline, a próxima
    # execução da página já lê de novo.
    return painel.ler(painel.MARTS)


# ---------------------------------------------------------------- cabeçalho
col_titulo, col_filtro = st.columns([2, 1], vertical_alignment="bottom")
col_titulo.title("Fórmula 1 · 75 anos em números")
# O filtro aparece acima do botão, mas só é montado depois da leitura;
# o botão precisa limpar o cache antes dela.
area_filtro = col_filtro.container()
if col_filtro.button("Recarregar dados"):
    carregar.clear()

try:
    dados = carregar()
except painel.DadosFaltando as e:
    if e.sem_banco:
        st.error(
            f"Não achei o {painel.CAMINHO_BANCO.name}. "
            f"Rode o pipeline e depois: `{painel.COMANDO_MARTS}`"
        )
    else:
        faltando = ", ".join(f"marts.{nome}" for nome in e.faltando)
        st.error(f"Faltando no banco: {faltando}. Rode: `{painel.COMANDO_MARTS}`")
    st.stop()

kpis = dados["kpis"].iloc[0]
abandonos = dados["abandonos"]

with area_filtro:
    inicio, fim = st.select_slider(
        "Temporadas",
        options=abandonos["ano"].tolist(),
        value=(abandonos["ano"].iloc[0], abandonos["ano"].iloc[-1]),
    )
    st.caption("os cartões e os rankings valem para a história inteira")

# ---------------------------------------------------------------- faixa 1
cartoes = [
    ("Temporadas", painel.numero(kpis["temporadas"])),
    ("Corridas · com resultado", painel.numero(kpis["corridas"])),
    ("Pilotos · com ao menos uma largada", painel.numero(kpis["pilotos"])),
    ("Equipes · com ao menos uma largada", painel.numero(kpis["equipes"])),
    ("Abandono · % das largadas", painel.pct(kpis["pct_abandono"], 1)),
    ("Vencedores diferentes", painel.numero(kpis["vencedores"])),
]
for coluna, (rotulo, valor) in zip(st.columns(6), cartoes, strict=True):
    coluna.metric(rotulo, valor)

# ---------------------------------------------------------------- faixa 2
recorte = abandonos[abandonos["ano"].between(inicio, fim)]
st.plotly_chart(painel.grafico_abandono(recorte), width="stretch")

# ---------------------------------------------------------------- faixa 3
c1, c2, c3 = st.columns(3)
c1.plotly_chart(
    painel.grafico_vitorias_pilotos(dados["ranking_pilotos"]), width="stretch"
)
c2.plotly_chart(
    painel.grafico_vitorias_equipes(dados["ranking_equipes"]), width="stretch"
)
c3.plotly_chart(
    painel.grafico_vitorias_nacionalidade(dados["por_nacionalidade"]), width="stretch"
)

# ---------------------------------------------------------------- faixa 4
c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.grafico_pole(dados["pole_vira_vitoria"]), width="stretch")
c2.plotly_chart(
    painel.grafico_motivos_abandono(dados["motivos_abandono"]), width="stretch"
)
c3.plotly_chart(
    painel.grafico_ganho_posicoes(dados["posicoes_ganhas"]), width="stretch"
)
