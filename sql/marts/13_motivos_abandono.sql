-- Por que os pilotos abandonam as corridas?
-- Grão: um status de abandono (refined.status_final.descricao).
-- Largou: exclui quem não se classificou para o grid (specs/marts.md, seção 5).
-- Abandono = largou, posicao nula e não foi desclassificado
-- ('Disqualified', 'Excluded'), como em 08_abandonos.
-- pct_abandonos = abandonos do motivo / abandonos da história inteira.
-- Empate em abandonos: ordem alfabética do motivo.
WITH abandonos AS (
    SELECT s.descricao AS motivo
    FROM refined.resultados   AS r
    JOIN refined.status_final AS s USING (id_status)
    WHERE NOT (r.voltas = 0 AND s.descricao IN (
        'Did not qualify', 'Did not prequalify', '107% Rule',
        'Withdrew', 'Injury', 'Injured'))
      AND r.posicao IS NULL
      AND s.descricao NOT IN ('Disqualified', 'Excluded')
)
SELECT
    motivo,
    count(*)                                              AS abandonos,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)    AS pct_abandonos
FROM abandonos
GROUP BY motivo
ORDER BY abandonos DESC, motivo
