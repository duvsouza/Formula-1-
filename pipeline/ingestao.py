r"""Ingestão: copia os 14 .csv da pasta raw/ para o schema raw do f1.duckdb.

Execução:
    uv run python -m pipeline.ingestao

1. ESCOPO E NOMES
   Schema de destino: raw. Entram os 14 arquivos, inclusive os que a
   primeira versão dos indicadores não usa (voltas, pit_stops,
   classificações).
   Por quê: raw é o espelho do que chegou. Escolher o que entra no projeto
   é decisão da transformação, que precisa do dado inteiro à mão.
   Tabelas em português (vocabulário digitado de memória nos JOINs);
   colunas com os nomes originais (raceId, driverId, positionText...),
   porque renomear coluna é decisão da transformação.

2. PROIBIÇÕES (a regra central desta etapa)
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Data e tempo de volta continuam texto. O texto \N, que o
   dataset usa para marcar ausência, continua sendo o texto \N.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   fica na passagem de raw para refined. Transformar \N em NULL é uma
   decisão, e decisão mora na transformação, onde fica escrita.

3. REEXECUÇÃO
   Rodar dez vezes dá o mesmo resultado que rodar uma: a tabela é recriada
   (CREATE OR REPLACE), nunca acrescentada.
   Por quê: reexecutar não pode duplicar linhas e inflar indicadores.

4. LEITURA DO ARQUIVO
   encoding="utf-8" declarado, nunca adivinhado.
   Por quê: drivers.csv e circuits.csv têm acentos e tremas (Pérez,
   Räikkönen, Hülkenberg, São Paulo); no Windows o palpite costuma ser
   cp1252, e os nomes saem embaralhados sem erro nenhum.
   Campo vazio, se existir, continua virando nulo, e não string vazia.

5. TIPAGEM
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Por quê: as colunas numéricas têm \N misturado com número; a inferência
   ou estoura ou trata cada tabela de um jeito. Tudo texto é previsível; a
   conversão acontece na transformação, como decisão registrada.

6. SAÍDA NA TELA
   Uma linha por tabela, com nome qualificado e contagem vinda do banco
   (não do DataFrame), milhar separado por ponto, e uma linha final com o
   total. stdout reconfigurado para utf-8.
   Por quê: essa saída é o único instrumento de conferência desta etapa, e
   no PowerShell do Windows acento sai embaralhado por padrão.

7. ERRO
   Antes de abrir o banco, verifica se os 14 arquivos existem. Faltando
   qualquer um: lista os que faltam, diz em que pasta procurou e encerra
   com sys.exit(1), sem ingerir nada.
   Por quê: ingerir 13 de 14 tabelas em silêncio produz um indicador
   errado que parece certo.

Separação: este módulo não importa ui.py, não sobe servidor, não abre
navegador e não depende da extensão ui do DuckDB.

Critérios de aceite:
- A execução imprime 14 linhas e um total.
- A contagem de cada tabela bate com
    SELECT count(*) FROM read_csv('raw/<arquivo>.csv', all_varchar = true);
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- DESCRIBE raw.resultados mostra todas as colunas como VARCHAR.
- SELECT count(*) FROM raw.resultados WHERE position = '\N' devolve > 0.
- SELECT forename, surname FROM raw.pilotos WHERE surname = 'Pérez'
  devolve a linha com o acento correto.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer
  tabela.
- O script termina sozinho e devolve o terminal.
"""

import sys
from pathlib import Path

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"

ARQUIVO_PARA_TABELA = {
    "circuits.csv": "circuitos",
    "constructor_results.csv": "resultados_equipes",
    "constructor_standings.csv": "classificacao_equipes",
    "constructors.csv": "equipes",
    "driver_standings.csv": "classificacao_pilotos",
    "drivers.csv": "pilotos",
    "lap_times.csv": "voltas",
    "pit_stops.csv": "pit_stops",
    "qualifying.csv": "classificatorio",
    "races.csv": "corridas",
    "results.csv": "resultados",
    "seasons.csv": "temporadas",
    "sprint_results.csv": "resultados_sprint",
    "status.csv": "status_final",
}


def ler_csv(caminho: Path) -> pd.DataFrame:
    r"""Lê um CSV do dataset como texto puro, sem inferir tipos.

    Args:
        caminho: arquivo .csv em UTF-8.

    Returns:
        DataFrame com todas as colunas str; só o campo vazio vira nulo, e
        textos como \N, "NA" ou "NULL" continuam como estão.
    """
    return pd.read_csv(
        caminho,
        encoding="utf-8",
        dtype=str,
        # A lista padrão de nulos do pandas transformaria textos como "NA",
        # "NULL" ou "None" em nulo, o que seria corrigir valor. Só o campo
        # vazio vira nulo; \N fica de fora de propósito.
        keep_default_na=False,
        na_values=[""],
    )


def formatar(n: int) -> str:
    """Formata um inteiro com milhar em ponto, ex.: 589081 -> "589.081"."""
    return f"{n:,}".replace(",", ".")


def main() -> None:
    """Executa a ingestão: confere os 14 CSVs, grava raw e imprime contagens."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    faltando = [a for a in ARQUIVO_PARA_TABELA if not (PASTA_RAW / a).is_file()]
    if faltando:
        print(f"Arquivos não encontrados em {PASTA_RAW}:", file=sys.stderr)
        for arquivo in faltando:
            print(f"  {arquivo}", file=sys.stderr)
        print("Nada foi gravado.", file=sys.stderr)
        sys.exit(1)

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        contagens = {}
        for arquivo, tabela in ARQUIVO_PARA_TABELA.items():
            df = ler_csv(PASTA_RAW / arquivo)
            contagens[f"{SCHEMA}.{tabela}"] = gravar(con, df, SCHEMA, tabela)
    finally:
        con.close()

    largura = max(len(nome) for nome in contagens)
    largura_n = len(formatar(sum(contagens.values())))
    for nome, n in contagens.items():
        print(f"{nome:<{largura}}  {formatar(n):>{largura_n}}")
    print(f"{'total':<{largura}}  {formatar(sum(contagens.values())):>{largura_n}}")


if __name__ == "__main__":
    main()
