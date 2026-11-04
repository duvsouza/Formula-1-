"""Conexão com o f1.duckdb, compartilhada por todas as etapas do pipeline.

Expõe exatamente:
    PASTA_RAW                        Path da pasta raw/ com os 14 .csv
    conectar()                       abre o f1.duckdb, criando se faltar
    criar_schema(con, nome)          CREATE SCHEMA IF NOT EXISTS
    gravar(con, df, schema, tabela)  grava e devolve a contagem lida do banco

D1. CAMINHOS
    PASTA_RAW e o f1.duckdb são resolvidos a partir da localização deste
    arquivo (a pasta acima de pipeline/), nunca do diretório corrente.
    Por quê: rodar de outra pasta não pode criar um f1.duckdb vazio no lugar
    errado, o que pareceria uma ingestão quebrada.

D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS
    Este módulo não lê CSV, não conhece nome de tabela, não imprime nada e
    não converte tipo.
    Por quê: transformação e marts também importam este arquivo; uma regra
    escondida aqui valeria para todas as etapas sem aparecer em nenhuma spec.

D3. gravar
    CREATE OR REPLACE TABLE schema.tabela com as colunas e os tipos do
    DataFrame, sem alterar nada: coluna str vira VARCHAR, nulo continua NULL.
    Não deixa view nem tabela temporária para trás.
    Devolve SELECT count(*) da tabela recém-gravada, lido do banco.
    Por quê: a contagem na tela tem que ser a do que foi gravado, não a do
    que estava na memória. CREATE OR REPLACE torna a gravação idempotente.

D4. CONEXÃO
    conectar() devolve a conexão aberta; quem chama é quem fecha.
    Nenhuma conexão global.
    Por quê: o .duckdb aceita um único processo escrevendo; uma conexão
    global aberta no import seguraria o lock sem ninguém saber de quem é.

Critérios de aceite:
- Importar pipeline.db não abre banco nem cria arquivo.
- conectar() chamado de dentro de outra pasta cria o f1.duckdb na raiz do
  projeto, e não na pasta corrente.
- gravar() com um DataFrame de 3 linhas devolve 3, e rodar duas vezes
  continua devolvendo 3.
"""

from pathlib import Path

import duckdb
import pandas as pd

_RAIZ = Path(__file__).resolve().parent.parent
_ARQUIVO_BANCO = _RAIZ / "f1.duckdb"

PASTA_RAW = _RAIZ / "raw"


def conectar() -> duckdb.DuckDBPyConnection:
    """Abre o f1.duckdb da raiz do projeto, criando o arquivo se faltar.

    Returns:
        Conexão de leitura e escrita; quem chama é responsável por fechar.
    """
    return duckdb.connect(str(_ARQUIVO_BANCO))


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    """Cria o schema se ele ainda não existir.

    Args:
        con: conexão aberta com o banco.
        nome: nome do schema.
    """
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"')


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    """Grava o DataFrame como tabela, substituindo a anterior.

    Args:
        con: conexão aberta com o banco.
        df: dados a gravar; os tipos das colunas viram os tipos da tabela.
        schema: schema de destino (precisa existir).
        tabela: nome da tabela.

    Returns:
        Número de linhas da tabela gravada, lido do banco.
    """
    destino = f'"{schema}"."{tabela}"'
    # O DuckDB lê o DataFrame por uma view registrada na conexão; ela é
    # removida no finally para não sobrar nada além da tabela gravada.
    view = "_gravar_df"
    con.register(view, df)
    try:
        con.execute(f'CREATE OR REPLACE TABLE {destino} AS SELECT * FROM "{view}"')
    finally:
        con.unregister(view)
    # fetchall, e não fetchone: no DuckDB 2 um resultado lido pela metade
    # bloqueia a conexão para o próximo comando de quem chamou.
    return con.execute(f"SELECT count(*) FROM {destino}").fetchall()[0][0]
