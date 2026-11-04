-- Qual a volta mais rápida em corrida de cada circuito, e de quem é?
-- Grão: um circuito com voltas registradas (refined.voltas começa em 1996).
-- Empate no tempo: vale o mais antigo.
-- O mesmo circuito pode ter mudado de traçado ao longo dos anos; o dataset
-- não registra o traçado, então o recorde é do circuito, não do traçado.
WITH voltas AS (
    SELECT
        c.id_circuito,
        c.ano,
        v.id_corrida,
        v.id_piloto,
        v.tempo_ms,
        v.tempo_texto
    FROM refined.voltas   AS v
    JOIN refined.corridas AS c USING (id_corrida)
),
recorde AS (
    -- Grão: um circuito.
    SELECT *
    FROM voltas
    QUALIFY row_number() OVER (
        PARTITION BY id_circuito ORDER BY tempo_ms, ano, id_corrida, id_piloto) = 1
),
corridas_circuito AS (
    SELECT id_circuito, count(DISTINCT id_corrida) AS corridas_com_voltas
    FROM voltas
    GROUP BY id_circuito
)
SELECT
    ci.id_circuito,
    ci.nome                         AS circuito,
    ci.pais,
    cc.corridas_com_voltas,
    r.tempo_ms                      AS recorde_ms,
    r.tempo_texto                   AS recorde,
    p.nome || ' ' || p.sobrenome    AS piloto,
    r.ano
FROM recorde           AS r
JOIN refined.circuitos AS ci USING (id_circuito)
JOIN refined.pilotos   AS p  USING (id_piloto)
JOIN corridas_circuito AS cc USING (id_circuito)
ORDER BY circuito
