-- Quem são os maiores pilotos da história em vitórias, títulos e pódios?
-- Grão: um piloto que largou ao menos uma corrida.
-- Largou: exclui quem não se classificou para o grid (specs/marts.md, seção 5).
-- Vitória, pódio e pole contam corridas distintas: em carro dividido (anos 50)
-- os dois pilotos recebem o crédito, uma vez cada.
-- Pole = largada 1 (cobre 1950-2024; classificatorio só começa em 1994).
-- Sem pontos: o sistema mudou ao longo dos anos e somar não compara.
WITH largadas AS (
    SELECT r.*, c.ano
    FROM refined.resultados   AS r
    JOIN refined.status_final AS s USING (id_status)
    JOIN refined.corridas     AS c USING (id_corrida)
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
titulos AS (
    -- Grão: um piloto campeão.
    SELECT cp.id_piloto, count(*) AS titulos
    FROM ultima AS u
    JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    WHERE cp.posicao = 1
    GROUP BY cp.id_piloto
),
por_piloto AS (
    SELECT
        id_piloto,
        min(ano)                                                AS primeira_temporada,
        max(ano)                                                AS ultima_temporada,
        count(DISTINCT id_corrida)                              AS corridas,
        count(DISTINCT id_corrida) FILTER (WHERE posicao = 1)   AS vitorias,
        count(DISTINCT id_corrida) FILTER (WHERE posicao <= 3)  AS podios,
        count(DISTINCT id_corrida) FILTER (WHERE largada = 1)   AS poles
    FROM largadas
    GROUP BY id_piloto
)
SELECT
    p.id_piloto,
    p.nome || ' ' || p.sobrenome                   AS piloto,
    p.nacionalidade,
    pp.primeira_temporada,
    pp.ultima_temporada,
    pp.corridas,
    pp.vitorias,
    pp.podios,
    pp.poles,
    coalesce(t.titulos, 0)                         AS titulos,
    round(100.0 * pp.vitorias / pp.corridas, 1)    AS pct_vitorias
FROM por_piloto      AS pp
JOIN refined.pilotos AS p USING (id_piloto)
LEFT JOIN titulos    AS t USING (id_piloto)
ORDER BY vitorias DESC, titulos DESC, podios DESC, piloto
