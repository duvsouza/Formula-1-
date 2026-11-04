r"""Transformação: lê o schema raw do f1.duckdb e grava o schema refined.

Execução:
    uv run python -m pipeline.transformacao

Fonte da verdade: specs/transformacao.md. Abaixo, cada regra e o seu motivo.

1. ESCOPO
   Lê de raw, escreve em refined. Nunca escreve em raw.
   Entram as 14 tabelas, com os mesmos nomes de raw. Nenhuma fica de fora.
   Por quê: o perfil de raw não achou tabela inutilizável (0 linhas
   duplicadas, 0 chaves estrangeiras órfãs, todos os formatos convertem).
   Deixar tabela de fora é decisão de indicador, e indicador mora nos marts.

2. NOMES
   Tabelas mantêm os nomes de raw. Colunas viram snake_case em português,
   pelo mapa em COLUNAS (abaixo), que é a transcrição literal da spec.
   Identificadores seguem id_<entidade>, para todo JOIN ser USING (id_x).
   Nenhuma coluna é removida e nenhuma é criada.
   Por quê: as tabelas já estão em português; "raceId" entre aspas ao lado
   de corridas é o pior dos dois mundos.

3. TIPOS
   Datas          DATE, formato %Y-%m-%d.
   Horas do dia   TIME, formato %H:%M:%S. Data e hora ficam separadas:
                  juntar exigiria decidir fuso, e hora é \N em 731 corridas.
   Pontos         DECIMAL(6,2): há pontos fracionados (0.5, 1.33), no
                  máximo 2 casas; somar DOUBLE não bate exato com a
                  classificação.
   Contagens e posições, id_*, durações já em ms   INTEGER.
   q1, q2, q3, fastestLapTime   texto M:SS.mmm convertido para INTEGER em
                  ms. Só ms é comparável e somável, e essas quatro não têm
                  coluna de ms correspondente em raw.
   Textos de exibição (tempo_texto, duracao_texto)   VARCHAR sem conversão:
                  "+5.478" é diferença para o líder, não duração; e a versão
                  em ms já existe ao lado.
   latitude, longitude, velocidade   DOUBLE (medidas contínuas).
   numero_carro, posicao_texto, codigo   VARCHAR: rótulos, nunca entram em
                  conta; posicao_texto mistura número e letra (R, D, E...).

4. CONVERSÃO QUE FALHA
   Para tudo (sys.exit(1)) sem gravar nenhuma tabela, imprimindo tabela,
   coluna, quantidade e até 5 exemplos.
   Por quê: hoje há 0 falhas nos formatos declarados; uma falha significa
   que a fonte mudou, e virar nulo esconderia isso dentro de um indicador.
   Falha = valor que não é \N nem nulo e não está no formato declarado.

5. DUPLICATAS
   Chave de cada tabela em CHAVES. (raceId, driverId) NÃO é chave de
   resultados: há 85 pares legítimos de carro compartilhado nos anos 50.
   Chave repetida com conteúdo idêntico: mantém uma linha e informa quantas
   saíram. Por quê: é cópia, descartar não perde informação.
   Chave repetida com conteúdo diferente: para tudo. Por quê: escolher qual
   linha está certa seria chute.

6. NULOS
   O texto \N vira NULL em todas as colunas, antes da conversão. Campo
   vazio continua NULL. Nenhum nulo é preenchido.
   Por quê: \N é "não se aplica / não registrado"; 0 em tempo ou posição
   seria um valor falso que entra em média.
   Só as colunas marcadas como nuláveis em COLUNAS podem ter nulo (a lista
   e o motivo de cada uma estão na spec, seção 6). Nulo em qualquer outra
   para tudo, pelo mesmo motivo da seção 4.
   largada = 0 (largou do pit lane) e rank_volta_mais_rapida = 0 são
   valores e continuam 0.

7. SAÍDA NA TELA
   Uma linha por tabela: nome qualificado, linhas em raw, linhas gravadas
   em refined (contagem lida do banco, devolvida por gravar), \N
   convertidos em NULL, duplicatas idênticas removidas. Milhar separado por
   ponto, linha final com os totais. stdout reconfigurado para utf-8.

REEXECUÇÃO E ERRO
   CREATE OR REPLACE (via gravar), nunca acrescenta.
   Faltando tabela em raw: lista quais, manda rodar a ingestão,
   sys.exit(1), sem gravar nada.
   Toda validação (seções 4, 5 e 6) roda nas 14 tabelas antes da primeira
   gravação. Por quê: parar na décima tabela deixaria refined metade nova,
   metade velha, e isso parece certo.

Critérios de aceite: ver specs/transformacao.md.
"""

import sys
from typing import NamedTuple

import duckdb
import pandas as pd

from pipeline.db import conectar, criar_schema, gravar

ORIGEM = "raw"
DESTINO = "refined"
AUSENTE = "\\N"
MAX_EXEMPLOS = 5


class Coluna(NamedTuple):
    """Uma coluna de raw e como ela chega em refined.

    Attributes:
        original: nome em raw (ex.: "raceId").
        nova: nome em refined (ex.: "id_corrida").
        tipo: chave de CONVERSOES que define formato e conversão.
        nulavel: se a coluna pode ter NULL em refined.
    """

    original: str
    nova: str
    tipo: str  # chave de CONVERSOES
    nulavel: bool = False


def c(original: str, nova: str, tipo: str, nulavel: bool = False) -> Coluna:
    """Atalho para declarar uma Coluna em uma linha no mapa COLUNAS."""
    return Coluna(original, nova, tipo, nulavel)


# Cada tipo: (expressão SQL que diz se o texto está no formato, conversão).
# {v} é o valor já com \N trocado por NULL.
# Inteiro e pontos validam por regex, e não só por try_cast: o cast de
# texto para número arredonda casas decimais em silêncio, e '1.7' virando 2
# seria exatamente a falha escondida que a seção 4 proíbe.
CONVERSOES = {
    "inteiro": (
        r"regexp_full_match({v}, '-?[0-9]+') AND try_cast({v} AS INTEGER) IS NOT NULL",
        "CAST({v} AS INTEGER)",
    ),
    "pontos": (
        (
            r"regexp_full_match({v}, '-?[0-9]+(\.[0-9]{{1,2}})?')"
            " AND try_cast({v} AS DECIMAL(6,2)) IS NOT NULL"
        ),
        "CAST({v} AS DECIMAL(6,2))",
    ),
    "double": ("try_cast({v} AS DOUBLE) IS NOT NULL", "CAST({v} AS DOUBLE)"),
    "data": (
        "try_strptime({v}, '%Y-%m-%d') IS NOT NULL",
        "CAST(strptime({v}, '%Y-%m-%d') AS DATE)",
    ),
    "hora": (
        "try_strptime({v}, '%H:%M:%S') IS NOT NULL",
        "CAST(strptime({v}, '%H:%M:%S') AS TIME)",
    ),
    # M:SS.mmm -> ms: minutos * 60000 + "SSmmm" lido como inteiro.
    "tempo_ms": (
        r"regexp_full_match({v}, '[0-9]+:[0-5][0-9]\.[0-9]{{3}}')",
        (
            "CAST(split_part({v}, ':', 1) AS INTEGER) * 60000"
            " + CAST(replace(split_part({v}, ':', 2), '.', '') AS INTEGER)"
        ),
    ),
    "texto": ("TRUE", "{v}"),
}

COLUNAS: dict[str, list[Coluna]] = {
    "circuitos": [
        c("circuitId", "id_circuito", "inteiro"),
        c("circuitRef", "ref_circuito", "texto"),
        c("name", "nome", "texto"),
        c("location", "cidade", "texto"),
        c("country", "pais", "texto"),
        c("lat", "latitude", "double"),
        c("lng", "longitude", "double"),
        c("alt", "altitude_m", "inteiro"),
        c("url", "url", "texto"),
    ],
    "equipes": [
        c("constructorId", "id_equipe", "inteiro"),
        c("constructorRef", "ref_equipe", "texto"),
        c("name", "nome", "texto"),
        c("nationality", "nacionalidade", "texto"),
        c("url", "url", "texto"),
    ],
    "pilotos": [
        c("driverId", "id_piloto", "inteiro"),
        c("driverRef", "ref_piloto", "texto"),
        c("number", "numero_carro", "texto", nulavel=True),
        c("code", "codigo", "texto", nulavel=True),
        c("forename", "nome", "texto"),
        c("surname", "sobrenome", "texto"),
        c("dob", "data_nascimento", "data"),
        c("nationality", "nacionalidade", "texto"),
        c("url", "url", "texto"),
    ],
    "temporadas": [
        c("year", "ano", "inteiro"),
        c("url", "url", "texto"),
    ],
    "corridas": [
        c("raceId", "id_corrida", "inteiro"),
        c("year", "ano", "inteiro"),
        c("round", "rodada", "inteiro"),
        c("circuitId", "id_circuito", "inteiro"),
        c("name", "nome", "texto"),
        c("date", "data", "data"),
        c("time", "hora", "hora", nulavel=True),
        c("url", "url", "texto"),
        c("fp1_date", "data_tl1", "data", nulavel=True),
        c("fp1_time", "hora_tl1", "hora", nulavel=True),
        c("fp2_date", "data_tl2", "data", nulavel=True),
        c("fp2_time", "hora_tl2", "hora", nulavel=True),
        c("fp3_date", "data_tl3", "data", nulavel=True),
        c("fp3_time", "hora_tl3", "hora", nulavel=True),
        c("quali_date", "data_classificatorio", "data", nulavel=True),
        c("quali_time", "hora_classificatorio", "hora", nulavel=True),
        c("sprint_date", "data_sprint", "data", nulavel=True),
        c("sprint_time", "hora_sprint", "hora", nulavel=True),
    ],
    "status_final": [
        c("statusId", "id_status", "inteiro"),
        c("status", "descricao", "texto"),
    ],
    "resultados": [
        c("resultId", "id_resultado", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("constructorId", "id_equipe", "inteiro"),
        c("number", "numero_carro", "texto", nulavel=True),
        c("grid", "largada", "inteiro"),
        c("position", "posicao", "inteiro", nulavel=True),
        c("positionText", "posicao_texto", "texto"),
        c("positionOrder", "ordem_chegada", "inteiro"),
        c("points", "pontos", "pontos"),
        c("laps", "voltas", "inteiro"),
        c("time", "tempo_texto", "texto", nulavel=True),
        c("milliseconds", "tempo_ms", "inteiro", nulavel=True),
        c("fastestLap", "volta_mais_rapida", "inteiro", nulavel=True),
        c("rank", "rank_volta_mais_rapida", "inteiro", nulavel=True),
        c("fastestLapTime", "volta_mais_rapida_ms", "tempo_ms", nulavel=True),
        c(
            "fastestLapSpeed",
            "velocidade_volta_mais_rapida_kmh",
            "double",
            nulavel=True,
        ),
        c("statusId", "id_status", "inteiro"),
    ],
    "resultados_sprint": [
        c("resultId", "id_resultado", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("constructorId", "id_equipe", "inteiro"),
        c("number", "numero_carro", "texto"),
        c("grid", "largada", "inteiro"),
        c("position", "posicao", "inteiro", nulavel=True),
        c("positionText", "posicao_texto", "texto"),
        c("positionOrder", "ordem_chegada", "inteiro"),
        c("points", "pontos", "pontos"),
        c("laps", "voltas", "inteiro"),
        c("time", "tempo_texto", "texto", nulavel=True),
        c("milliseconds", "tempo_ms", "inteiro", nulavel=True),
        c("fastestLap", "volta_mais_rapida", "inteiro", nulavel=True),
        c("fastestLapTime", "volta_mais_rapida_ms", "tempo_ms", nulavel=True),
        c("statusId", "id_status", "inteiro"),
    ],
    "resultados_equipes": [
        c("constructorResultsId", "id_resultado_equipe", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("constructorId", "id_equipe", "inteiro"),
        c("points", "pontos", "pontos"),
        c("status", "status", "texto", nulavel=True),
    ],
    "classificacao_pilotos": [
        c("driverStandingsId", "id_classificacao_piloto", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("points", "pontos", "pontos"),
        c("position", "posicao", "inteiro"),
        c("positionText", "posicao_texto", "texto"),
        c("wins", "vitorias", "inteiro"),
    ],
    "classificacao_equipes": [
        c("constructorStandingsId", "id_classificacao_equipe", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("constructorId", "id_equipe", "inteiro"),
        c("points", "pontos", "pontos"),
        c("position", "posicao", "inteiro"),
        c("positionText", "posicao_texto", "texto"),
        c("wins", "vitorias", "inteiro"),
    ],
    "classificatorio": [
        c("qualifyId", "id_classificatorio", "inteiro"),
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("constructorId", "id_equipe", "inteiro"),
        c("number", "numero_carro", "texto"),
        c("position", "posicao", "inteiro"),
        c("q1", "q1_ms", "tempo_ms", nulavel=True),
        c("q2", "q2_ms", "tempo_ms", nulavel=True),
        c("q3", "q3_ms", "tempo_ms", nulavel=True),
    ],
    "voltas": [
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("lap", "volta", "inteiro"),
        c("position", "posicao", "inteiro"),
        c("time", "tempo_texto", "texto"),
        c("milliseconds", "tempo_ms", "inteiro"),
    ],
    "pit_stops": [
        c("raceId", "id_corrida", "inteiro"),
        c("driverId", "id_piloto", "inteiro"),
        c("stop", "parada", "inteiro"),
        c("lap", "volta", "inteiro"),
        c("time", "hora", "hora"),
        c("duration", "duracao_texto", "texto"),
        c("milliseconds", "duracao_ms", "inteiro"),
    ],
}

# Chaves em nomes originais, porque a checagem roda sobre raw.
CHAVES: dict[str, list[str]] = {
    "circuitos": ["circuitId"],
    "equipes": ["constructorId"],
    "pilotos": ["driverId"],
    "temporadas": ["year"],
    "corridas": ["raceId"],
    "status_final": ["statusId"],
    "resultados": ["resultId"],
    "resultados_sprint": ["resultId"],
    "resultados_equipes": ["constructorResultsId"],
    "classificacao_pilotos": ["driverStandingsId"],
    "classificacao_equipes": ["constructorStandingsId"],
    "classificatorio": ["qualifyId"],
    "voltas": ["raceId", "driverId", "lap"],
    "pit_stops": ["raceId", "driverId", "stop"],
}


def q(nome: str) -> str:
    """Põe um identificador SQL entre aspas duplas."""
    return f'"{nome}"'


def valor(col: Coluna) -> str:
    r"""Expressão SQL da coluna original com o texto \N trocado por NULL."""
    return f"NULLIF({q(col.original)}, '{AUSENTE}')"


def formatar(n: int) -> str:
    """Formata um inteiro com milhar em ponto, ex.: 589081 -> "589.081"."""
    return f"{n:,}".replace(",", ".")


def tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Lista as tabelas de COLUNAS que não existem no schema raw."""
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?", [ORIGEM]
        ).fetchall()
    }
    return [t for t in COLUNAS if t not in existentes]


def validar(
    con: duckdb.DuckDBPyConnection, tabela: str
) -> tuple[list[str], dict[str, int]]:
    r"""Confere formatos, nulos e chaves de uma tabela de raw. Não grava nada.

    Args:
        con: conexão aberta com o banco.
        tabela: nome da tabela (chave de COLUNAS).

    Returns:
        Tupla (erros, números). erros é a lista de mensagens, vazia se a
        tabela pode ser transformada; números tem "raw" (linhas lidas),
        "ausentes" (\N encontrados) e "duplicatas" (cópias idênticas).
    """
    erros = []
    origem = f"{q(ORIGEM)}.{q(tabela)}"
    colunas = COLUNAS[tabela]

    # Uma única passada pela tabela: por coluna, quantos \N, quantos nulos
    # depois do NULLIF e quantos valores fora do formato.
    partes = []
    for col in colunas:
        v = valor(col)
        formato_ok = CONVERSOES[col.tipo][0].format(v=v)
        partes += [
            f"count(*) FILTER (WHERE {q(col.original)} = '{AUSENTE}')",
            f"count(*) FILTER (WHERE {v} IS NULL)",
            f"count(*) FILTER (WHERE {v} IS NOT NULL AND NOT ({formato_ok}))",
        ]
    linha = con.execute(
        f"SELECT count(*), {', '.join(partes)} FROM {origem}"
    ).fetchall()[0]
    n_raw, por_coluna = linha[0], linha[1:]

    n_ausentes = 0
    for i, col in enumerate(colunas):
        ausentes, nulos, falhas = por_coluna[3 * i : 3 * i + 3]
        n_ausentes += ausentes
        if falhas:
            v = valor(col)
            formato_ok = CONVERSOES[col.tipo][0].format(v=v)
            exemplos = [
                r[0]
                for r in con.execute(
                    f"SELECT DISTINCT {v} FROM {origem} "
                    f"WHERE {v} IS NOT NULL AND NOT ({formato_ok}) "
                    f"ORDER BY 1 LIMIT {MAX_EXEMPLOS}"
                ).fetchall()
            ]
            erros.append(
                f"{tabela}.{col.original}: {formatar(falhas)} valor(es) fora do "
                f"formato '{col.tipo}'. Exemplos: {exemplos}"
            )
        if nulos and not col.nulavel:
            erros.append(
                f"{tabela}.{col.original}: {formatar(nulos)} nulo(s) em coluna "
                "que a spec declara NOT NULL"
            )

    # DISTINCT * remove as cópias idênticas; se depois disso a chave ainda
    # repete, é porque o conteúdo difere.
    chave = ", ".join(q(k) for k in CHAVES[tabela])
    n_distintas, n_chaves_conflito = con.execute(
        f"""
        WITH distintas AS (SELECT DISTINCT * FROM {origem})
        SELECT
            (SELECT count(*) FROM distintas),
            (SELECT count(*) FROM (
                SELECT {chave} FROM distintas GROUP BY ALL HAVING count(*) > 1
            ))
        """
    ).fetchall()[0]
    if n_chaves_conflito:
        exemplos = con.execute(
            f"SELECT {chave} FROM (SELECT DISTINCT * FROM {origem}) "
            f"GROUP BY ALL HAVING count(*) > 1 ORDER BY ALL LIMIT {MAX_EXEMPLOS}"
        ).fetchall()
        erros.append(
            f"{tabela}: {formatar(n_chaves_conflito)} chave(s) ({chave}) repetida(s) "
            f"com conteúdo diferente. Exemplos: {exemplos}"
        )

    numeros = {
        "raw": n_raw,
        "ausentes": n_ausentes,
        "duplicatas": n_raw - n_distintas,
    }
    return erros, numeros


def transformar(con: duckdb.DuckDBPyConnection, tabela: str) -> pd.DataFrame:
    """Converte uma tabela de raw para os nomes e tipos de refined.

    Supõe que validar() não achou erro nessa tabela.

    Args:
        con: conexão aberta com o banco.
        tabela: nome da tabela (chave de COLUNAS).

    Returns:
        DataFrame sem cópias idênticas, ordenado pela chave, com dtypes
        Arrow para preservar DECIMAL, DATE e TIME na gravação.
    """
    colunas = COLUNAS[tabela]
    selecao = ",\n    ".join(
        f"{CONVERSOES[col.tipo][1].format(v=valor(col))} AS {q(col.nova)}"
        for col in colunas
    )
    novas = {col.original: col.nova for col in colunas}
    ordem = ", ".join(q(novas[k]) for k in CHAVES[tabela])
    sql = (
        f"SELECT {selecao}\n"
        f"FROM (SELECT DISTINCT * FROM {q(ORIGEM)}.{q(tabela)})\n"
        f"ORDER BY {ordem}"
    )
    # Via Arrow, e não .df(): o .df() do DuckDB entrega DECIMAL como float e
    # DATE como timestamp, e gravar() grava os tipos que o DataFrame tiver.
    return con.sql(sql).to_arrow_table().to_pandas(types_mapper=pd.ArrowDtype)


def main() -> None:
    """Executa a etapa: valida as 14 tabelas de raw e só então grava refined."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas não encontradas no schema {ORIGEM}:", file=sys.stderr)
            for tabela in faltando:
                print(f"  {tabela}", file=sys.stderr)
            print(
                "Rode a ingestão antes: uv run python -m pipeline.ingestao",
                file=sys.stderr,
            )
            print("Nada foi gravado.", file=sys.stderr)
            sys.exit(1)

        erros, numeros = [], {}
        for tabela in COLUNAS:
            erros_tabela, numeros[tabela] = validar(con, tabela)
            erros += erros_tabela
        if erros:
            print("Transformação interrompida:", file=sys.stderr)
            for erro in erros:
                print(f"  {erro}", file=sys.stderr)
            print("Nada foi gravado.", file=sys.stderr)
            sys.exit(1)

        criar_schema(con, DESTINO)
        for tabela in COLUNAS:
            df = transformar(con, tabela)
            numeros[tabela]["refined"] = gravar(con, df, DESTINO, tabela)
    finally:
        con.close()

    cabecalho = ["tabela", "raw", "refined", "\\N->NULL", "dup removidas"]
    campos = ["raw", "refined", "ausentes", "duplicatas"]
    linhas = [
        [f"{DESTINO}.{t}"] + [formatar(n[k]) for k in campos]
        for t, n in numeros.items()
    ]
    linhas.append(
        ["total"] + [formatar(sum(n[k] for n in numeros.values())) for k in campos]
    )
    larguras = [max(len(str(lin[i])) for lin in [cabecalho, *linhas]) for i in range(5)]
    for linha in [cabecalho, *linhas]:
        print(
            f"{linha[0]:<{larguras[0]}}  "
            + "  ".join(f"{linha[i]:>{larguras[i]}}" for i in range(1, 5))
        )


if __name__ == "__main__":
    main()
