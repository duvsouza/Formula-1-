CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público de
Fórmula 1 (Ergast, 1950–2024). Trabalho com spec-driven development: a spec
abaixo é a fonte da verdade e o código é consequência dela. Não acrescente
requisito que não esteja escrito aqui. Se algo estiver ambíguo, pergunte
antes de escrever código.

STACK
- Python 3.14, uv, DuckDB 2 (f1.duckdb na raiz do projeto), pandas 3

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py: conectar(), criar_schema(con, nome), gravar(con, df, schema, tabela)
O schema raw, com 14 tabelas, todas as colunas VARCHAR. O texto \N marca
ausência e ainda não foi convertido (decisão desta etapa).

ARTEFATO A PRODUZIR
pipeline/transformacao.py, executável com:
  uv run python -m pipeline.transformacao

SPEC

1. ESCOPO
   Lê de raw, escreve em refined. Nunca escreve em raw.

   Tabelas que entram (14, mesmos nomes de raw):
     circuitos, equipes, pilotos, temporadas, corridas, status_final,
     resultados, resultados_sprint, resultados_equipes,
     classificacao_pilotos, classificacao_equipes, classificatorio,
     voltas, pit_stops

   Tabelas que ficam de fora, e por quê: nenhuma.
   Por quê: o perfil de raw não encontrou tabela inutilizável (0 linhas
   duplicadas, 0 chaves estrangeiras órfãs, todos os formatos convertem).
   voltas (589.081 linhas) é a única cara, e cabe com folga no DuckDB.
   Deixar uma tabela de fora é decisão de indicador, e indicador mora nos
   marts.

2. NOMES
   Tabelas: mantêm os nomes de raw.
   Colunas: renomeadas para snake_case em português, com o mapa abaixo.
   Por quê: as tabelas já estão em português; JOIN com "raceId" entre aspas
   ao lado de corridas é o pior dos dois mundos. Identificadores seguem o
   padrão id_<entidade>, para que todo JOIN seja USING (id_x).

   Mapa coluna_original -> coluna_nova:

   Comuns (valem em toda tabela onde aparecem):
     circuitId -> id_circuito      constructorId -> id_equipe
     driverId  -> id_piloto        raceId        -> id_corrida
     statusId  -> id_status        year          -> ano
     url       -> url              name          -> nome
     nationality -> nacionalidade  points        -> pontos
     position  -> posicao          positionText  -> posicao_texto
     wins      -> vitorias         number        -> numero_carro
     time      -> ver por tabela   milliseconds  -> ver por tabela

   circuitos: circuitRef -> ref_circuito, location -> cidade,
     country -> pais, lat -> latitude, lng -> longitude, alt -> altitude_m
   equipes: constructorRef -> ref_equipe
   pilotos: driverRef -> ref_piloto, code -> codigo, forename -> nome,
     surname -> sobrenome, dob -> data_nascimento
     (pilotos.number -> numero_carro)
   temporadas: (só comuns)
   corridas: round -> rodada, date -> data, time -> hora,
     fp1_date -> data_tl1, fp1_time -> hora_tl1,
     fp2_date -> data_tl2, fp2_time -> hora_tl2,
     fp3_date -> data_tl3, fp3_time -> hora_tl3,
     quali_date -> data_classificatorio, quali_time -> hora_classificatorio,
     sprint_date -> data_sprint, sprint_time -> hora_sprint
   status_final: status -> descricao
   resultados e resultados_sprint: resultId -> id_resultado,
     grid -> largada, positionOrder -> ordem_chegada, laps -> voltas,
     time -> tempo_texto, milliseconds -> tempo_ms,
     fastestLap -> volta_mais_rapida, fastestLapTime -> volta_mais_rapida_ms,
     rank -> rank_volta_mais_rapida (só resultados),
     fastestLapSpeed -> velocidade_volta_mais_rapida_kmh (só resultados)
   resultados_equipes: constructorResultsId -> id_resultado_equipe,
     status -> status
   classificacao_pilotos: driverStandingsId -> id_classificacao_piloto
   classificacao_equipes: constructorStandingsId -> id_classificacao_equipe
   classificatorio: qualifyId -> id_classificatorio, q1 -> q1_ms,
     q2 -> q2_ms, q3 -> q3_ms
   voltas: lap -> volta, time -> tempo_texto, milliseconds -> tempo_ms
   pit_stops: stop -> parada, lap -> volta, time -> hora,
     duration -> duracao_texto, milliseconds -> duracao_ms

   Nenhuma coluna é removida e nenhuma é criada.

3. TIPOS
   Datas:        DATE   formato declarado: %Y-%m-%d
                 (corridas.data, data_tl1..3, data_classificatorio,
                  data_sprint; pilotos.data_nascimento)
   Horas do dia: TIME   formato declarado: %H:%M:%S
                 (corridas.hora e hora_*; pit_stops.hora)
                 Por quê: data e hora ficam separadas como em raw; juntar em
                 TIMESTAMP exigiria decidir fuso, e hora é \N em 731 corridas.
   Pontos (no lugar de dinheiro):  DECIMAL(6,2)
                 motivo: há pontos fracionados (0.5, 1.33, 6.14...), no
                 máximo 2 casas, máximo 575 por temporada. Somar DOUBLE dá
                 0,30000000000000004; o total do campeonato tem que bater
                 exato com a classificação.
   Contagens e posições: INTEGER
                 (vitorias, voltas, volta, parada, rodada, largada, posicao,
                  ordem_chegada, rank_volta_mais_rapida, volta_mais_rapida,
                  altitude_m, ano)
   Durações:     INTEGER em milissegundos
                 tempo_ms, duracao_ms: cast direto (máximo 15.090.540, cabe).
                 q1_ms, q2_ms, q3_ms, volta_mais_rapida_ms: texto no formato
                 M:SS.mmm convertido para ms (minutos*60000 + segundos*1000).
                 Por quê: só ms é comparável e somável; essas quatro colunas
                 não têm coluna de ms correspondente em raw.
   Textos de exibição: VARCHAR, sem conversão
                 resultados.tempo_texto ("+5.478" é diferença para o líder,
                 não duração), voltas.tempo_texto, pit_stops.duracao_texto
                 (já existe a versão em ms ao lado; há valores como
                 "18:06.875" em paradas sob bandeira vermelha).
   Medidas contínuas: DOUBLE
                 (latitude, longitude, velocidade_volta_mais_rapida_kmh)
   Identificadores de linha (id_*): INTEGER
                 motivo: são chaves substitutas sequenciais, sem zero à
                 esquerda; INTEGER deixa o JOIN mais barato.
   Identificadores que parecem número: VARCHAR
                 numero_carro, posicao_texto, codigo
                 motivo: são rótulos, nunca entram em conta. posicao_texto
                 mistura número com letra (R, D, E, W, F, N);
                 numero_carro é o que está pintado no carro.

4. CONVERSÃO QUE FALHA
   Para tudo: sys.exit(1), sem gravar nenhuma tabela.
   Antes de sair, imprime tabela, coluna, quantidade de falhas e até 5
   valores de exemplo.
   motivo: o perfil de raw dá 0 falhas para todos os formatos declarados
   acima. Uma falha significa que a fonte mudou; virar nulo esconderia isso
   dentro de um indicador que parece certo.
   Falha = valor diferente de \N e de nulo que não converte no tipo/formato
   declarado.

5. DUPLICATAS
   Chave de cada tabela:
     circuitos: id_circuito            equipes: id_equipe
     pilotos: id_piloto                temporadas: ano
     corridas: id_corrida              status_final: id_status
     resultados: id_resultado          resultados_sprint: id_resultado
     resultados_equipes: id_resultado_equipe
     classificacao_pilotos: id_classificacao_piloto
     classificacao_equipes: id_classificacao_equipe
     classificatorio: id_classificatorio
     voltas: (id_corrida, id_piloto, volta)
     pit_stops: (id_corrida, id_piloto, parada)
   Atenção: (id_corrida, id_piloto) NÃO é chave de resultados. Há 85 pares
   repetidos legítimos (carro compartilhado nos anos 50–60: o mesmo piloto
   em dois carros na mesma corrida).

   Chave repetida com conteúdo idêntico: mantém uma linha e informa na tela
   quantas foram removidas. (Hoje: 0.)
   Chave repetida com conteúdo diferente: para tudo, sys.exit(1), listando
   tabela e chaves. (Hoje: 0.)
   Por quê: linha idêntica é cópia, descartar não perde informação. Conteúdo
   diferente exige escolher qual está certa, e isso seria chute.

6. NULOS
   Regra geral: o texto \N vira NULL em todas as colunas, antes da conversão
   de tipo. Campo vazio (já NULL em raw) continua NULL. Nenhum nulo é
   preenchido (nem com 0, nem com texto).
   Por quê: \N é "não se aplica / não registrado"; 0 em tempo ou posição
   seria um valor falso que entra em média.

   Colunas que podem ser nulas (todas as demais são NOT NULL; nulo nelas =
   para tudo, sys.exit(1)):
     pilotos.numero_carro (802), pilotos.codigo (757): números fixos e
       códigos de 3 letras só existem a partir de 2014 / anos 2000.
     corridas.hora (731) e todos os data_*/hora_* de treinos, classificatório
       e sprint: não registrados antes de 2021 ou corrida sem sprint.
     resultados.numero_carro (6), resultados_sprint e resultados:
       posicao (10.953 / 15): piloto não classificado; usar ordem_chegada
       para ordenar.
       tempo_texto, tempo_ms (19.079 / 20): não terminou ou volta(s) atrás.
       volta_mais_rapida, volta_mais_rapida_ms, velocidade_* (18.507 / 9),
       rank_volta_mais_rapida (18.249): não medidos antes de 2004.
     resultados_equipes.status (12.608): só existe quando a equipe foi
       desclassificada ('D').
     classificatorio.q2_ms (4.647), q3_ms (6.865): piloto eliminado antes
       da sessão (somatório de \N e campo vazio em raw); q1_ms (156).

   Valores que parecem ausência mas NÃO viram nulo:
     resultados.largada = 0 (1.638): largou do pit lane; é um valor.
     resultados.rank_volta_mais_rapida = 0 (258, 2011–2024): mantido como 0;
       significado não documentado no dataset.

7. SAÍDA NA TELA
   Por tabela, uma linha: nome qualificado (refined.<tabela>), linhas em
   raw, linhas gravadas em refined (contagem lida do banco, devolvida por
   gravar), quantidade de \N convertidos em NULL, duplicatas idênticas
   removidas. Milhar separado por ponto. Uma linha final com os totais.
   stdout reconfigurado para utf-8.

REEXECUÇÃO E ERRO (iguais à etapa 1)
   CREATE OR REPLACE, nunca acrescenta.
   Faltando tabela em raw: lista quais, manda rodar a ingestão
   (uv run python -m pipeline.ingestao), sys.exit(1), sem gravar nada.

CRITÉRIOS DE ACEITE
   - A execução imprime 14 linhas e um total.
   - Contagens em refined iguais às de raw: circuitos 77, equipes 212,
     pilotos 861, temporadas 75, corridas 1.125, status_final 139,
     resultados 26.759, resultados_sprint 360, resultados_equipes 12.625,
     classificacao_pilotos 34.863, classificacao_equipes 13.391,
     classificatorio 10.494, voltas 589.081, pit_stops 11.371;
     total 701.433.
   - Nenhuma coluna VARCHAR de refined contém o texto \N (0 linhas).
   - SELECT count(*) FROM refined.resultados WHERE posicao IS NULL = 10.953.
   - SELECT count(*) FROM refined.resultados WHERE tempo_ms IS NULL = 19.079.
   - SELECT count(*) FROM refined.classificatorio WHERE q2_ms IS NULL = 4.647,
     e WHERE q3_ms IS NULL = 6.865.
   - SELECT sum(pontos) FROM refined.resultados = 53187.05 (exato).
   - SELECT max(pontos) FROM refined.classificacao_pilotos = 575.00.
   - SELECT count(*) FROM refined.resultados WHERE largada = 0 = 1.638.
   - min/max de corridas.data = 1950-05-13 / 2024-12-08;
     min/max de pilotos.data_nascimento = 1896-12-28 / 2005-05-08.
   - DESCRIBE de cada tabela mostra os tipos da seção 3 e os nomes da
     seção 2; nenhum nome original (raceId etc.) sobrevive.
   - Para toda linha de voltas: tempo_ms bate com tempo_texto convertido
     (0 divergências). Idem pit_stops.duracao_ms x duracao_texto.
   - Trocar um valor de raw.corridas.data por 'abc' faz o script parar com
     exit 1 apontando corridas.date, sem gravar nada.
   - Remover raw.voltas faz o script parar listando voltas e mandando rodar
     a ingestão.
   - Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA
1. A spec como docstring no topo do arquivo, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
