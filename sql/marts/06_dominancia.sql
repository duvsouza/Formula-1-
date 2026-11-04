-- O quanto o campeão dominou cada temporada?
-- Grão: uma temporada.
-- pct_vitorias_campeao = corridas que o campeão venceu / corridas do ano.
-- vencedores_distintos mede o equilíbrio: quantos pilotos venceram ao menos uma.
-- Vitórias vêm de resultados (corridas distintas), como no ranking de pilotos.
WITH ultima AS (
    SELECT c.ano, arg_max(c.id_corrida, c.rodada) AS id_corrida
    FROM refined.corridas AS c
    SEMI JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    GROUP BY c.ano
),
campeao AS (
    -- Grão: uma temporada.
    SELECT u.ano, cp.id_piloto
    FROM ultima AS u
    JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    WHERE cp.posicao = 1
),
vitorias AS (
    -- Grão: um piloto vencedor numa corrida.
    SELECT DISTINCT c.ano, r.id_corrida, r.id_piloto
    FROM refined.resultados AS r
    JOIN refined.corridas   AS c USING (id_corrida)
    WHERE r.posicao = 1
),
por_ano AS (
    SELECT
        v.ano,
        count(DISTINCT v.id_corrida) FILTER (WHERE v.id_piloto = ch.id_piloto) AS vitorias_campeao,
        count(DISTINCT v.id_piloto)                                           AS vencedores_distintos
    FROM vitorias     AS v
    JOIN campeao      AS ch USING (ano)
    GROUP BY v.ano
),
corridas_ano AS (
    SELECT ano, count(*) AS corridas
    FROM refined.corridas
    GROUP BY ano
)
SELECT
    ca.ano,
    p.nome || ' ' || p.sobrenome                            AS campeao,
    ca.corridas,
    pa.vitorias_campeao,
    round(100.0 * pa.vitorias_campeao / ca.corridas, 1)     AS pct_vitorias_campeao,
    pa.vencedores_distintos
FROM corridas_ano    AS ca
JOIN campeao         AS ch USING (ano)
JOIN refined.pilotos AS p  ON p.id_piloto = ch.id_piloto
JOIN por_ano         AS pa USING (ano)
ORDER BY ca.ano
