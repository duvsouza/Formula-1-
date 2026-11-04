-- Quais nacionalidades mais venceram na Fórmula 1?
-- Grão: uma nacionalidade de piloto que largou ao menos uma corrida.
-- corridas_vencidas conta corridas distintas: dois pilotos da mesma
-- nacionalidade dividindo um carro vencedor contam uma vez.
-- titulos = títulos de pilotos; pilotos_campeoes = quantos pilotos diferentes.
WITH largadas AS (
    SELECT r.*
    FROM refined.resultados   AS r
    JOIN refined.status_final AS s USING (id_status)
    WHERE NOT (r.voltas = 0 AND s.descricao IN (
        'Did not qualify', 'Did not prequalify', '107% Rule',
        'Withdrew', 'Injury', 'Injured'))
),
ultima AS (
    SELECT c.ano, arg_max(c.id_corrida, c.rodada) AS id_corrida
    FROM refined.corridas AS c
    SEMI JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    GROUP BY c.ano
),
campeoes AS (
    -- Grão: uma temporada.
    SELECT u.ano, cp.id_piloto
    FROM ultima AS u
    JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    WHERE cp.posicao = 1
),
por_nacionalidade AS (
    SELECT
        p.nacionalidade,
        count(DISTINCT l.id_piloto)                                AS pilotos,
        count(DISTINCT l.id_corrida) FILTER (WHERE l.posicao = 1)  AS corridas_vencidas
    FROM largadas        AS l
    JOIN refined.pilotos AS p USING (id_piloto)
    GROUP BY p.nacionalidade
),
titulos AS (
    SELECT
        p.nacionalidade,
        count(*)                        AS titulos,
        count(DISTINCT ch.id_piloto)    AS pilotos_campeoes
    FROM campeoes        AS ch
    JOIN refined.pilotos AS p USING (id_piloto)
    GROUP BY p.nacionalidade
)
SELECT
    n.nacionalidade,
    n.pilotos,
    n.corridas_vencidas,
    coalesce(t.titulos, 0)             AS titulos,
    coalesce(t.pilotos_campeoes, 0)    AS pilotos_campeoes
FROM por_nacionalidade AS n
LEFT JOIN titulos      AS t USING (nacionalidade)
ORDER BY corridas_vencidas DESC, titulos DESC, nacionalidade
