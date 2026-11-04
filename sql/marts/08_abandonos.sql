-- Quantos pilotos não terminaram as corridas, e por quê?
-- Grão: uma temporada.
-- Largou: exclui quem não se classificou para o grid (specs/marts.md, seção 5).
-- Abandono = largou, sem posição final, e não foi desclassificado.
-- Desclassificação ('Disqualified', 'Excluded') é contada à parte.
-- Causa principal: status mais frequente entre os abandonos; empate pela
-- ordem alfabética.
WITH largadas AS (
    SELECT
        c.ano,
        s.descricao,
        r.posicao IS NOT NULL                          AS classificado,
        s.descricao IN ('Disqualified', 'Excluded')    AS desclassificado
    FROM refined.resultados   AS r
    JOIN refined.status_final AS s USING (id_status)
    JOIN refined.corridas     AS c USING (id_corrida)
    WHERE NOT (r.voltas = 0 AND s.descricao IN (
        'Did not qualify', 'Did not prequalify', '107% Rule',
        'Withdrew', 'Injury', 'Injured'))
),
causa_principal AS (
    -- Grão: uma temporada.
    SELECT ano, descricao, count(*) AS vezes
    FROM largadas
    WHERE NOT classificado AND NOT desclassificado
    GROUP BY ano, descricao
    QUALIFY row_number() OVER (PARTITION BY ano ORDER BY vezes DESC, descricao) = 1
),
por_ano AS (
    SELECT
        ano,
        count(*)                                                          AS largadas,
        count(*) FILTER (WHERE classificado)                              AS classificados,
        count(*) FILTER (WHERE NOT classificado AND NOT desclassificado)  AS abandonos,
        count(*) FILTER (WHERE desclassificado)                           AS desclassificados
    FROM largadas
    GROUP BY ano
)
SELECT
    a.ano,
    a.largadas,
    a.classificados,
    a.abandonos,
    a.desclassificados,
    round(100.0 * a.abandonos / a.largadas, 1)    AS pct_abandono,
    c.descricao                                   AS causa_principal,
    c.vezes                                       AS vezes_causa_principal
FROM por_ano              AS a
LEFT JOIN causa_principal AS c USING (ano)
ORDER BY a.ano
