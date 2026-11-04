-- Quais são as maiores equipes da história em vitórias, títulos e pódios?
-- Grão: uma equipe que largou ao menos uma corrida.
-- corridas, vitorias e poles contam corridas distintas.
-- podios conta carros: uma equipe pode ter dois carros no pódio da mesma corrida.
-- titulos = títulos de construtores (existem desde 1958).
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
    SEMI JOIN refined.classificacao_equipes AS ce USING (id_corrida)
    GROUP BY c.ano
),
titulos AS (
    -- Grão: uma equipe campeã.
    SELECT ce.id_equipe, count(*) AS titulos
    FROM ultima AS u
    JOIN refined.classificacao_equipes AS ce USING (id_corrida)
    WHERE ce.posicao = 1
    GROUP BY ce.id_equipe
),
por_equipe AS (
    SELECT
        id_equipe,
        min(ano)                                                AS primeira_temporada,
        max(ano)                                                AS ultima_temporada,
        count(DISTINCT id_corrida)                              AS corridas,
        count(DISTINCT id_corrida) FILTER (WHERE posicao = 1)   AS vitorias,
        count(*) FILTER (WHERE posicao <= 3)                    AS podios,
        count(DISTINCT id_corrida) FILTER (WHERE largada = 1)   AS poles
    FROM largadas
    GROUP BY id_equipe
)
SELECT
    e.id_equipe,
    e.nome                                         AS equipe,
    e.nacionalidade,
    pe.primeira_temporada,
    pe.ultima_temporada,
    pe.corridas,
    pe.vitorias,
    pe.podios,
    pe.poles,
    coalesce(t.titulos, 0)                         AS titulos,
    round(100.0 * pe.vitorias / pe.corridas, 1)    AS pct_vitorias
FROM por_equipe      AS pe
JOIN refined.equipes AS e USING (id_equipe)
LEFT JOIN titulos    AS t USING (id_equipe)
ORDER BY vitorias DESC, titulos DESC, podios DESC, equipe
