-- Quanto dura um pit stop, e quantos são feitos por corrida?
-- Grão: uma temporada com pit stops registrados (2011 em diante).
-- Duração = tempo no pit lane, da entrada à saída (não só o carro parado).
-- Mediana, e não média: paradas sob bandeira vermelha duram até 51 minutos
-- e puxam a média para 85 s, contra mediana de 23,6 s.
-- paradas_acima_60s mostra quantas são esse caso.
SELECT
    c.ano,
    count(*)                                              AS paradas,
    count(DISTINCT ps.id_corrida)                         AS corridas,
    round(count(*) / count(DISTINCT ps.id_corrida), 1)    AS paradas_por_corrida,
    round(median(ps.duracao_ms) / 1000, 3)                AS mediana_s,
    count(*) FILTER (WHERE ps.duracao_ms > 60000)         AS paradas_acima_60s
FROM refined.pit_stops AS ps
JOIN refined.corridas  AS c USING (id_corrida)
GROUP BY c.ano
ORDER BY c.ano
