CONTEXTO
Pipeline de dados em Python sobre o dataset público de Fórmula 1 (Ergast,
1950–2024). Spec-driven development: esta spec é a fonte da verdade e o
código é consequência dela. Não acrescente requisito que não esteja escrito
aqui. Se algo estiver ambíguo, pergunte antes de escrever código.

STACK
- Python 3.14, uv, DuckDB 2 (f1.duckdb na raiz do projeto)

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py: conectar(), criar_schema(con, nome)
pipeline/transformacao.py: COLUNAS (as 14 tabelas de refined são as chaves)
O schema refined, com 14 tabelas tipadas (specs/transformacao.md).

ARTEFATOS A PRODUZIR
pipeline/marts.py, executável com:
  uv run python -m pipeline.marts
sql/marts/NN_<nome>.sql, um arquivo por indicador (lista na seção 5).

SPEC

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
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>.
   Tira espaços e um ponto e vírgula do final, e nada mais. O Python não
   altera, não monta e não completa a SQL.
   Cada .sql lê só de refined, nunca de outro mart.
   Por quê: a regra de negócio mora inteira no arquivo .sql, e cada arquivo
   se explica sozinho, sem depender da ordem de execução.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.campeoes_pilotos   75 linhas
   Linha final com o número de marts e o total de linhas.
   stdout reconfigurado para utf-8. Impresso só depois do COMMIT.

4. ERRO
   - Faltando tabela em refined: lista quais, manda rodar
     "uv run python -m pipeline.transformacao", sys.exit(1).
   - sql/marts/ sem nenhum .sql: avisa e sys.exit(1).
     Por quê: rodar sem arquivo apagaria todos os marts sem criar nenhum.
   - Arquivo sem prefixo NN_ ou dois arquivos com o mesmo nome de tabela
     (sem diferenciar maiúsculas): lista e sys.exit(1) antes de executar
     qualquer SQL.
   - .sql que falha: nome do arquivo + mensagem do DuckDB, não executa os
     seguintes, sys.exit(1).
   - Mart com 0 linhas: nome e sys.exit(1).
     Por quê: mart vazio é quase sempre um JOIN que não casou.
   - Tudo numa transação: qualquer falha devolve o marts da última execução
     que deu certo.

5. INDICADORES
   Definições comuns (repetidas em cada .sql que as usa, com comentário):
   - Corrida = linha de refined.corridas. Sprint não conta como corrida nem
     como vitória: resultados_sprint fica fora de todos os marts.
   - Largou = linha de refined.resultados, exceto status 'Did not qualify',
     'Did not prequalify', '107% Rule', 'Withdrew', 'Injury' ou 'Injured'
     com voltas = 0.
     Por quê: em 1950–1992 até 30+ inscritos por corrida não se
     classificavam; contar essas linhas como corrida disputada infla
     estreantes e equipes pequenas.
   - Vitória = posicao = 1; pódio = posicao <= 3; pole = largada = 1.
     Contadas como corridas distintas (count DISTINCT id_corrida).
     Por quê: em 3 corridas há dois vencedores e em 9 há duas poles (carro
     dividido nos anos 50); cada piloto recebe o crédito, uma vez.
     Pole vem de largada, e não de classificatorio, porque classificatorio
     só começa em 1994.
   - Campeão = posicao = 1 em classificacao_pilotos/classificacao_equipes na
     última rodada do ano que tem classificação publicada.
   - Abandono = largou, posicao nula e status diferente de 'Disqualified' e
     'Excluded' (desclassificação é contada à parte).
   - Pontos nunca são somados entre temporadas: o sistema mudou (8 pontos
     por vitória em 1950, 10 em 2009, 25 desde 2010). Rankings de carreira
     ordenam por vitórias, títulos e pódios.

   Arquivos, grão e pergunta:
   01_kpis                  1 linha     Tamanho do dataset: temporadas,
                                        corridas, circuitos, pilotos, equipes,
                                        primeira e última corrida.
   02_campeoes_pilotos      temporada   Campeão, pontos, vitórias no ano,
                                        corridas no ano, vantagem para o vice.
   03_campeoes_equipes      temporada   O mesmo para construtores (1958+,
                                        primeiro ano do título).
   04_ranking_pilotos       piloto que largou ao menos uma vez
                                        Corridas, vitórias, pódios, poles,
                                        títulos, % de vitórias, primeira e
                                        última temporada.
   05_ranking_equipes       equipe que largou ao menos uma vez
                                        Corridas, vitórias, pódios (por carro),
                                        poles, títulos, % de vitórias.
   06_dominancia            temporada   Vitórias do campeão / corridas do ano,
                                        e quantos pilotos diferentes venceram.
   07_pole_vira_vitoria     década      Corridas, corridas em que o pole
                                        venceu, %.
   08_abandonos             temporada   Largadas, classificados, abandonos,
                                        desclassificados, % de abandono, causa
                                        mais frequente (empate: ordem
                                        alfabética) e quantas vezes.
   09_pit_stops             temporada (2011+, início de pit_stops)
                                        Paradas, paradas por corrida, mediana
                                        da duração em segundos, paradas acima
                                        de 60 s.
                                        Mediana, e não média: 517 paradas sob
                                        bandeira vermelha (até 51 min) levam a
                                        média a 85 s contra mediana de 23,6 s.
   10_recorde_por_circuito  circuito com voltas registradas (1996+, início
                                        de voltas). Volta mais rápida em
                                        corrida: tempo, piloto, ano. Empate:
                                        o mais antigo. O mesmo circuito pode
                                        ter mudado de traçado; o mart não
                                        separa traçados (o dataset não tem
                                        essa informação).
   11_posicoes_ganhas       piloto com 50+ corridas classificadas
                                        Média de (largada - posicao), largada
                                        e chegada médias. Só classificados com
                                        largada > 0 (largada 0 = pit lane, sem
                                        posição de grid).
                                        Por quê do corte em 50: com poucas
                                        corridas a média é ruído.
   12_por_nacionalidade     nacionalidade de piloto que largou
                                        Pilotos, corridas vencidas, títulos,
                                        pilotos campeões.

CRITÉRIOS DE ACEITE
   - A execução imprime 12 linhas ✓ e o total.
   - marts.kpis: 75 temporadas, 1.125 corridas, 77 circuitos.
   - marts.campeoes_pilotos: 75 linhas; 2024 = Max Verstappen, 437 pontos;
     1950 = Nino Farina, 30 pontos.
   - marts.campeoes_equipes: 67 linhas (1958–2024); 2024 = McLaren,
     1958 = Vanwall.
   - marts.ranking_pilotos: Lewis Hamilton com 105 vitórias e 7 títulos;
     Michael Schumacher com 91 vitórias e 7 títulos (agrupar por id_piloto,
     não por sobrenome: Ralf tem 6).
   - Nenhum mart soma pontos de temporadas diferentes.
   - Um .sql com erro de sintaxe para tudo, mostra o nome do arquivo, e
     marts fica exatamente como antes.
   - Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA
1. A spec do runner como docstring no topo de pipeline/marts.py.
2. Cada .sql começa com a pergunta, o grão e as definições que usa.
3. Uma lista final do que você assumiu e que não estava na spec.
