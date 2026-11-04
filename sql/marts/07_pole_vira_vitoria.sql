-- Largar na pole garante a vitória? Isso mudou com o tempo?
-- Grão: uma década (1950 = 1950 a 1959).
-- Pole = largada 1. Uma corrida conta como "pole venceu" se algum piloto
-- largou em 1 e terminou em 1 (em carro dividido há corridas com duas poles).
WITH por_corrida AS (
    -- Grão: uma corrida.
    SELECT
        c.id_corrida,
        c.ano // 10 * 10                            AS decada,
        bool_or(r.largada = 1 AND r.posicao = 1)    AS pole_venceu
    FROM refined.corridas   AS c
    JOIN refined.resultados AS r USING (id_corrida)
    GROUP BY c.id_corrida, decada
)
SELECT
    decada,
    count(*)                                                           AS corridas,
    count(*) FILTER (WHERE pole_venceu)                                AS pole_venceu,
    round(100.0 * count(*) FILTER (WHERE pole_venceu) / count(*), 1)   AS pct_pole_venceu
FROM por_corrida
GROUP BY decada
ORDER BY decada
