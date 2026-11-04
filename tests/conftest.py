"""Fixtures compartilhadas.

Os testes unitários nunca tocam o f1.duckdb do projeto: cada um recebe um
banco novo em tmp_path, apontado por monkeypatch nos módulos que resolvem o
caminho sozinhos (pipeline.db, painel).
"""

from pathlib import Path

import duckdb
import pytest

import painel
from pipeline import db
from pipeline.transformacao import COLUNAS

RAIZ = Path(__file__).resolve().parent.parent
BANCO_REAL = RAIZ / "f1.duckdb"


@pytest.fixture
def banco(tmp_path, monkeypatch) -> Path:
    """Caminho de um f1.duckdb temporário (ainda não criado)."""
    caminho = tmp_path / "f1.duckdb"
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", caminho)
    monkeypatch.setattr(painel, "CAMINHO_BANCO", caminho)
    return caminho


@pytest.fixture
def con():
    """Conexão DuckDB em memória, fechada ao fim do teste."""
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


def criar_raw_vazio(conexao: duckdb.DuckDBPyConnection) -> None:
    """Cria as 14 tabelas de raw, só VARCHAR e sem linhas."""
    conexao.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for tabela, colunas in COLUNAS.items():
        definicao = ", ".join(f'"{c.original}" VARCHAR' for c in colunas)
        conexao.execute(f"CREATE TABLE raw.{tabela} ({definicao})")
