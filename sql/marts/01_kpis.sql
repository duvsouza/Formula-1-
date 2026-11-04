-- Qual é o tamanho do dataset?
-- Grão: o dataset inteiro, uma linha.
-- pilotos e equipes contam só quem largou ao menos uma corrida
-- (definição de "largou" em specs/marts.md, seção 5).
WITH largadas AS (
    SELECT r.*
    FROM refined.resultados   AS r
    JOIN refined.status_final AS s USING (id_status)
    WHERE NOT (r.voltas = 0 AND s.descricao IN (
        'Did not qualify', 'Did not prequalify', '107% Rule',
        'Withdrew', 'Injury', 'Injured'))
)
SELECT
    (SELECT count(*) FROM refined.temporadas)          AS temporadas,
    (SELECT count(*) FROM refined.corridas)            AS corridas,
    (SELECT count(*) FROM refined.circuitos)           AS circuitos,
    (SELECT count(DISTINCT id_piloto) FROM largadas)   AS pilotos,
    (SELECT count(DISTINCT id_equipe) FROM largadas)   AS equipes,
    (SELECT min(data) FROM refined.corridas)           AS primeira_corrida,
    (SELECT max(data) FROM refined.corridas)           AS ultima_corrida
