"""Etapa 3: cria o schema marts a partir dos arquivos de sql/marts/.

Execução:
    uv run python -m pipeline.marts

Fonte da verdade: specs/marts.md. As definições dos indicadores (largou,
vitória, pole, campeão, abandono) estão lá e no cabeçalho de cada .sql.

1. ESCOPO
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em
   refined. O schema marts é apagado e recriado a cada execução
   (DROP SCHEMA IF EXISTS marts CASCADE).
   Por quê: um mart cujo arquivo foi apagado não pode continuar existindo
   no banco.

2. UM ARQUIVO, UMA TABELA
   Lê todos os sql/marts/*.sql em ordem alfabética do nome do arquivo.
   Nome da tabela = nome do arquivo sem extensão e sem o prefixo NN_:
     sql/marts/02_campeoes_pilotos.sql -> marts.campeoes_pilotos
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final, e nada mais.
   O Python não altera, não monta e não completa a SQL.
   Por quê: a regra de negócio mora inteira no arquivo .sql.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.campeoes_pilotos   75 linhas
   Linha final com o número de marts e o total de linhas.
   stdout reconfigurado para utf-8.
   Por quê: a contagem lida do banco é a do que foi gravado; no PowerShell
   do Windows, acento e ✓ saem embaralhados sem o utf-8.

4. ERRO
   - Faltando tabela em refined: lista quais, manda rodar a transformação,
     sys.exit(1).
     Por quê: um mart sobre refined incompleto falha ou, pior, sai errado.
   - sql/marts/ sem nenhum .sql: avisa e sys.exit(1).
     Por quê: rodar sem arquivo apagaria todos os marts sem criar nenhum.
   - Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois
     arquivos que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
     Por quê: sem prefixo não há nome de tabela definido; dois arquivos com
     o mesmo nome fariam um sobrescrever o outro em silêncio.
   - .sql que falha: nome do arquivo e mensagem do DuckDB, não executa os
     seguintes, sys.exit(1).
     Por quê: o nome do arquivo diz onde consertar; a mensagem diz o quê.
   - Mart com zero linhas: nome e sys.exit(1).
     Por quê: mart vazio é quase sempre um JOIN que não casou.
   - Tudo numa transação: qualquer falha devolve o marts da última execução
     que deu certo.
     Por quê: um schema pela metade quebra quem consome sem avisar.

Critérios de aceite: ver specs/marts.md.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import conectar, criar_schema
from pipeline.transformacao import COLUNAS

ORIGEM = "refined"
DESTINO = "marts"
TABELAS_REFINED = list(COLUNAS)

# Resolvida a partir deste arquivo, como o f1.duckdb em db.py: rodar de
# outra pasta não pode achar "nenhum arquivo" por engano.
_RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = _RAIZ / "sql" / "marts"

# NN_ = exatamente dois dígitos e um sublinhado; o resto do nome é a tabela.
_PREFIXO = re.compile(r"^\d{2}_(.+)$")


class FalhaEtapa(Exception):
    """Erro já explicado em texto; main imprime, desfaz e sai com 1."""


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _erro(*linhas: str) -> None:
    for linha in linhas:
        print(linha, file=sys.stderr)
    sys.exit(1)


def _relativo(arquivo: Path) -> str:
    return arquivo.relative_to(_RAIZ).as_posix()


def _tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [t for t in TABELAS_REFINED if t not in existentes]


def _validar_nomes(arquivos: list[Path]) -> list[tuple[Path, str]]:
    """Devolve (arquivo, nome da tabela) ou encerra listando os problemas."""
    sem_prefixo = []
    por_nome: dict[str, list[Path]] = {}
    for arquivo in arquivos:
        achado = _PREFIXO.match(arquivo.stem)
        if not achado:
            sem_prefixo.append(arquivo)
            continue
        # O DuckDB não diferencia maiúscula de minúscula em nome de tabela:
        # 01_Kpis e 02_kpis viram a mesma tabela.
        por_nome.setdefault(achado.group(1).lower(), []).append(arquivo)

    repetidos = {n: a for n, a in por_nome.items() if len(a) > 1}
    if sem_prefixo or repetidos:
        linhas = []
        if sem_prefixo:
            linhas.append("Arquivos sem o prefixo NN_ (ex.: 01_nome.sql):")
            linhas += [f"  {_relativo(a)}" for a in sem_prefixo]
        for nome, lista in repetidos.items():
            linhas.append(f"Arquivos que dão a mesma tabela {DESTINO}.{nome}:")
            linhas += [f"  {_relativo(a)}" for a in lista]
        linhas.append("Nenhuma SQL foi executada.")
        _erro(*linhas)

    return [(a, _PREFIXO.match(a.stem).group(1)) for a in arquivos]


def _criar_mart(con: duckdb.DuckDBPyConnection, arquivo: Path, nome: str) -> int:
    sql = arquivo.read_text(encoding="utf-8").rstrip().removesuffix(";")
    destino = f'{DESTINO}."{nome}"'
    try:
        con.execute(f"CREATE TABLE {destino} AS {sql}")
    except duckdb.Error as e:
        raise FalhaEtapa(f"Falhou: {_relativo(arquivo)}\n{e}") from e
    # fetchall, não fetchone: no DuckDB 2 um resultado lido pela metade
    # bloqueia a conexão para o próximo comando.
    linhas = con.execute(f"SELECT count(*) FROM {destino}").fetchall()[0][0]
    if linhas == 0:
        raise FalhaEtapa(
            f"Mart vazio: {DESTINO}.{nome} ({_relativo(arquivo)}) voltou com 0 linhas."
        )
    return linhas


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = _tabelas_faltando(con)
        if faltando:
            _erro(
                f"Tabelas faltando no schema {ORIGEM}:",
                *(f"  {ORIGEM}.{t}" for t in faltando),
                'Rode antes: "uv run python -m pipeline.transformacao"',
            )

        # Ordena pelo nome do arquivo, não pela ordem do sistema de
        # arquivos, que muda entre Windows e Linux.
        arquivos = sorted(PASTA_SQL.glob("*.sql"), key=lambda a: a.name)
        if not arquivos:
            _erro(f"Nenhum arquivo .sql em {_relativo(PASTA_SQL)}/.")

        marts = _validar_nomes(arquivos)

        # DROP, CREATE SCHEMA e todos os CREATE TABLE na mesma transação:
        # o ROLLBACK devolve o marts da última execução que deu certo.
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(f"DROP SCHEMA IF EXISTS {DESTINO} CASCADE")
            criar_schema(con, DESTINO)
            relatorio = [(nome, _criar_mart(con, a, nome)) for a, nome in marts]
            con.execute("COMMIT")
        except FalhaEtapa as e:
            con.execute("ROLLBACK")
            _erro(str(e), f"Nada foi gravado; {DESTINO} continua como estava.")

        # Imprime só depois do COMMIT: um ✓ antes de uma falha seria a
        # promessa de uma tabela que o ROLLBACK desfez.
        largura_nome = max(len(f"{DESTINO}.{n}") for n, _ in relatorio) + 2
        largura_num = max(len(_milhar(q)) for _, q in relatorio)
        for nome, linhas in relatorio:
            print(
                f"✓ {f'{DESTINO}.{nome}':<{largura_nome}}"
                f"{_milhar(linhas):>{largura_num}} {'linha' if linhas == 1 else 'linhas'}"
            )
        total = sum(q for _, q in relatorio)
        print(
            f"{len(relatorio)} {'mart' if len(relatorio) == 1 else 'marts'}, "
            f"{_milhar(total)} {'linha' if total == 1 else 'linhas'}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
