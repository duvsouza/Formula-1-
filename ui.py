"""Abre o f1.duckdb no navegador pela extensão ui do DuckDB.

Execução:
    uv run python ui.py

U1. O QUE FAZ
    Abre o f1.duckdb da raiz do projeto, instala e carrega a extensão ui
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador.
    Por quê: explorar o banco pelo navegador em vez de ler tabela no
    terminal.

U2. FICA DE PÉ ATÉ CTRL+C
    A extensão serve enquanto a conexão estiver viva. O script mantém o
    processo rodando, imprime a URL e "Ctrl+C para encerrar"; no Ctrl+C
    fecha a conexão e sai limpo, sem traceback.
    Por quê: o .duckdb aceita um único processo escrevendo. Com o ui.py de
    pé, a ingestão falha com "Could not set lock on file". Saber desligar o
    servidor faz parte da ferramenta.

U3. NÃO CRIA BANCO
    Se f1.duckdb não existir, avisa que é preciso rodar a ingestão antes e
    encerra com sys.exit(1). Por isso não usa conectar() de pipeline/db.py,
    que cria o arquivo quando ele falta.
    Por quê: um banco vazio aberto no navegador parece ingestão quebrada.

U4. SEPARAÇÃO
    Não importa pipeline/ingestao.py, e a ingestão não importa este
    arquivo: a ingestão não sobe servidor, não abre navegador e não depende
    da extensão ui.

U5. SAÍDA NA TELA
    stdout reconfigurado para utf-8, como na ingestão.

Critérios de aceite:
- Abre o navegador em localhost:4213 e o schema raw aparece com as 14
  tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda
  sem erro de lock.
- Renomear f1.duckdb faz o script parar com a mensagem, sem criar arquivo.
"""

import sys
import time
from pathlib import Path

import duckdb

# Resolvido pela localização deste arquivo, como em pipeline/db.py, para não
# depender da pasta de onde o script é chamado.
ARQUIVO_BANCO = Path(__file__).resolve().parent / "f1.duckdb"
URL = "http://localhost:4213"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # Checado antes do connect, porque duckdb.connect cria o arquivo se ele
    # não existir.
    if not ARQUIVO_BANCO.is_file():
        print(f"Banco não encontrado: {ARQUIVO_BANCO}", file=sys.stderr)
        print("Rode a ingestão antes: uv run python -m pipeline.ingestao", file=sys.stderr)
        sys.exit(1)

    con = None
    try:
        con = duckdb.connect(str(ARQUIVO_BANCO))
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        con.execute("CALL start_ui()")
        print(f"DuckDB UI em {URL}")
        print("Ctrl+C para encerrar")
        # sleep em laço, e não Event().wait(): no Windows uma espera sem
        # timeout não é interrompida pelo Ctrl+C.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if con is not None:
            con.close()
    print("Encerrado.")


if __name__ == "__main__":
    main()
