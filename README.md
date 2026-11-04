# Fórmula 1 · 75 anos em números

Pipeline de dados em Python + DuckDB sobre o dataset público de Fórmula 1
(Ergast, 1950–2024), com um painel em Streamlit no final.

Os dados passam por três camadas dentro de um único arquivo `f1.duckdb`:

```
raw/*.csv ──► raw ──► refined ──► marts ──► painel (Streamlit)
           ingestão  transformação  marts.py    app.py
```

O projeto segue **spec-driven development**: cada etapa tem uma spec (em
[specs/](specs/) ou na docstring do próprio módulo) que é a fonte da verdade,
e o código é consequência dela. Toda regra vem acompanhada do seu "por quê".

## Stack

- Python 3.14, gerenciado com [uv](https://docs.astral.sh/uv/)
- DuckDB 2
- pandas 3
- Streamlit + Plotly (painel)
- ruff e pytest (dev)

## Como rodar

```bash
uv sync                                   # instala as dependências

uv run python -m pipeline.ingestao        # 1. raw/*.csv -> schema raw
uv run python -m pipeline.transformacao   # 2. raw -> schema refined
uv run python -m pipeline.marts           # 3. refined -> schema marts

uv run streamlit run app.py               # painel no navegador
```

Opcional, para explorar o banco pelo navegador (DuckDB UI em
`http://localhost:4213`):

```bash
uv run python ui.py                       # Ctrl+C para encerrar
```

> O `.duckdb` aceita um único processo escrevendo. Com o `ui.py` de pé, as
> etapas do pipeline falham com *"Could not set lock on file"*. Encerre-o
> antes de rodar o pipeline. O painel abre o banco em modo somente leitura e
> fecha a conexão logo após ler, então não atrapalha.

Todas as etapas são idempotentes: rodar duas vezes produz exatamente a mesma
saída.

## Estrutura

```
Formula1/
├── raw/                    14 CSVs do dataset Ergast (entrada)
├── pipeline/
│   ├── db.py               conexão com o f1.duckdb, compartilhada pelas etapas
│   ├── ingestao.py         etapa 1: CSV -> raw
│   ├── transformacao.py    etapa 2: raw -> refined
│   └── marts.py            etapa 3: refined -> marts (executa sql/marts/*.sql)
├── sql/marts/              um .sql por indicador (NN_<nome>.sql)
├── specs/
│   ├── transformacao.md    spec da etapa 2
│   └── marts.md            spec da etapa 3 e definições dos indicadores
├── painel.py               leitura dos marts, formatação e gráficos (sem Streamlit)
├── app.py                  página Streamlit
├── ui.py                   abre o f1.duckdb na DuckDB UI
├── tests/                  testes (pytest), um arquivo por módulo
└── pyproject.toml          dependências e configuração do ruff e do pytest
```

O arquivo `f1.duckdb` é gerado pelo pipeline na raiz do projeto e não é
versionado. Todos os caminhos são resolvidos a partir da localização dos
arquivos `.py`, então os comandos funcionam de qualquer pasta.

## Etapas

### 1. Ingestão — `raw`

[pipeline/ingestao.py](pipeline/ingestao.py) copia os 14 CSVs para o schema
`raw`, com tabelas renomeadas para português e colunas com os nomes originais.

| arquivo                   | tabela                      |
|---------------------------|-----------------------------|
| circuits.csv              | raw.circuitos               |
| constructors.csv          | raw.equipes                 |
| drivers.csv               | raw.pilotos                 |
| seasons.csv               | raw.temporadas              |
| races.csv                 | raw.corridas                |
| status.csv                | raw.status_final            |
| results.csv               | raw.resultados              |
| sprint_results.csv        | raw.resultados_sprint       |
| constructor_results.csv   | raw.resultados_equipes      |
| driver_standings.csv      | raw.classificacao_pilotos   |
| constructor_standings.csv | raw.classificacao_equipes   |
| qualifying.csv            | raw.classificatorio         |
| lap_times.csv             | raw.voltas                  |
| pit_stops.csv             | raw.pit_stops               |

Regra central: `raw` é o espelho do que chegou. **Nenhuma** conversão de tipo,
linha descartada, coluna renomeada ou valor corrigido. Tudo entra como
`VARCHAR` e o texto `\N` (ausência no dataset) continua sendo `\N`. Leitura
sempre em UTF-8 (acentos como Pérez, Räikkönen, São Paulo). Se faltar
qualquer CSV, o script para antes de gravar qualquer coisa.

### 2. Transformação — `refined`

[pipeline/transformacao.py](pipeline/transformacao.py) — spec em
[specs/transformacao.md](specs/transformacao.md).

- **Nomes**: colunas em `snake_case` português; identificadores no padrão
  `id_<entidade>`, para todo JOIN ser `USING (id_x)`.
- **Tipos**: datas `DATE`, horas `TIME` (separadas, sem decidir fuso), pontos
  `DECIMAL(6,2)` (somas exatas), contagens/posições/ids `INTEGER`, tempos
  `M:SS.mmm` convertidos para milissegundos `INTEGER`, coordenadas e
  velocidade `DOUBLE`; rótulos como `numero_carro` e `posicao_texto` ficam
  `VARCHAR`.
- **Nulos**: `\N` vira `NULL`; nenhum nulo é preenchido. Só colunas declaradas
  como nuláveis podem ter nulo.
- **Duplicatas**: cópia idêntica é removida e informada; chave repetida com
  conteúdo diferente para tudo.
- **Falhas**: valor fora do formato declarado, ou nulo onde não pode, para a
  execução com exemplos — **sem gravar nenhuma tabela**. Toda validação roda
  nas 14 tabelas antes da primeira gravação.

Saída esperada: 14 tabelas, 701.433 linhas no total (voltas sozinha tem
589.081).

### 3. Marts — `marts`

[pipeline/marts.py](pipeline/marts.py) — spec em
[specs/marts.md](specs/marts.md).

Cada arquivo `sql/marts/NN_<nome>.sql` vira a tabela `marts.<nome>`
(`CREATE TABLE marts.<nome> AS <conteúdo do arquivo>`). Toda regra de negócio
mora no `.sql`; o Python não monta nem altera SQL. O schema `marts` é apagado
e recriado a cada execução, dentro de uma transação: qualquer falha (SQL com
erro, mart vazio, nome inválido ou duplicado) faz `ROLLBACK` e mantém o
`marts` da última execução bem-sucedida.

| arquivo                     | grão                         | pergunta |
|-----------------------------|------------------------------|----------|
| 01_kpis                     | 1 linha                      | Tamanho do dataset, % de abandono, vencedores diferentes |
| 02_campeoes_pilotos         | temporada                    | Campeão, pontos, vitórias, vantagem para o vice |
| 03_campeoes_equipes         | temporada (1958+)            | O mesmo para construtores |
| 04_ranking_pilotos          | piloto que largou            | Corridas, vitórias, pódios, poles, títulos |
| 05_ranking_equipes          | equipe que largou            | Corridas, vitórias, pódios, poles, títulos |
| 06_dominancia               | temporada                    | % de vitórias do campeão, vencedores distintos |
| 07_pole_vira_vitoria        | década                       | Em quantas corridas o pole venceu |
| 08_abandonos                | temporada                    | Largadas, abandonos, desclassificações, causa principal |
| 09_pit_stops                | temporada (2011+)            | Paradas por corrida, mediana da duração |
| 10_recorde_por_circuito     | circuito (1996+)             | Volta mais rápida em corrida |
| 11_posicoes_ganhas          | piloto com 50+ classificações| Média de posições ganhas da largada à chegada |
| 12_por_nacionalidade        | nacionalidade                | Vitórias, títulos, pilotos campeões |
| 13_motivos_abandono         | status de abandono           | Abandonos por motivo e % do total |

#### Definições usadas nos indicadores

- **Corrida**: linha de `refined.corridas`. Sprint não conta como corrida nem
  como vitória.
- **Largou**: linha de `refined.resultados`, exceto quem não se classificou
  para o grid (`Did not qualify`, `Did not prequalify`, `107% Rule`,
  `Withdrew`, `Injury`, `Injured` com 0 voltas).
- **Vitória** = `posicao = 1`; **pódio** = `posicao <= 3`; **pole** =
  `largada = 1`. Contadas como corridas distintas (carro dividido nos anos 50
  dá crédito a cada piloto, uma vez).
- **Campeão**: posição 1 na classificação da última rodada do ano com
  classificação publicada.
- **Abandono**: largou, sem posição final, e não foi desclassificado
  (`Disqualified`/`Excluded` contam à parte).
- **Pontos nunca são somados entre temporadas** — o sistema de pontuação
  mudou. Rankings de carreira ordenam por vitórias, títulos e pódios.

Cada `.sql` começa com um comentário repetindo a pergunta, o grão e as
definições que usa.

## Painel

[app.py](app.py) é a página Streamlit; [painel.py](painel.py) concentra
leitura, formatação e gráficos e não importa Streamlit (pode ser reaproveitado
num relatório HTML).

- Lê 8 marts com `SELECT * FROM marts.<nome>` e **não faz nenhum cálculo**:
  só ordena, filtra linhas, pega as primeiras n e formata. Número novo na tela
  exige um `.sql` novo em `sql/marts/`.
- Layout: seis cartões de KPI; taxa de abandono por temporada (com filtro de
  temporadas); top 10 de vitórias por piloto, equipe e nacionalidade; a pole
  vence? por década; motivos de abandono; ganho de posições.
- Cada gráfico traz no título o número do `.sql` que o define (ex.:
  `08 · Abandono por temporada`).
- Números no padrão brasileiro (milhar com ponto, decimal com vírgula),
  independente do locale da máquina.
- Botão **Recarregar dados** limpa o cache depois de rodar o pipeline de novo.
  Se o banco ou algum mart faltar, a página mostra o que falta e o comando
  para gerar.

## Testes e qualidade

```bash
uv run pytest                      # todos os testes
uv run pytest -m "not integracao"  # só os unitários (não precisam do f1.duckdb)
uv run pytest -m integracao        # só os critérios de aceite no banco real

uv run ruff format .               # formata (PEP 8, linha de 88 colunas)
uv run ruff check .                # lint: PEP 8, PEP 257, imports, bugs comuns
```

Os testes ficam em [tests/](tests/), um arquivo por módulo:

- **Unitários** (`test_db`, `test_ingestao`, `test_transformacao`,
  `test_marts`, `test_painel`): cada teste usa um `f1.duckdb` temporário
  (fixture `banco` em [tests/conftest.py](tests/conftest.py)) e nunca toca o
  banco do projeto. Cobrem as regras das specs: conversões e formatos
  rejeitados, nulos, duplicatas, "nada é gravado" quando algo falha,
  `ROLLBACK` dos marts, idempotência e formatação brasileira dos números.
- **Integração** (`test_integracao`, marcados com `integracao`): conferem no
  `f1.duckdb` real os critérios de aceite de
  [specs/transformacao.md](specs/transformacao.md) e
  [specs/marts.md](specs/marts.md) (contagens, somas exatas, campeões,
  rankings). Abrem o banco somente leitura e são pulados se ele não existir
  ou estiver travado por outro processo.

O ruff está configurado no `pyproject.toml` com as regras `E`/`W`
(pycodestyle/PEP 8), `F`, `I` (ordem dos imports), `N` (nomes), `D`
(docstrings no estilo Google, PEP 257), `UP`, `B` e `SIM`.

## Explorando com SQL

Além da DuckDB UI (`ui.py`), o banco pode ser consultado direto:

```sql
FROM marts.ranking_pilotos LIMIT 10;
FROM marts.campeoes_pilotos WHERE ano = 2024;
```

O arquivo `.mcp.json` (local, não versionado) configura o servidor MCP do
DuckDB para consultas somente leitura no `f1.duckdb` a partir do Claude Code.
