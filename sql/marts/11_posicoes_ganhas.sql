-- Quais pilotos mais ganham posições entre a largada e a chegada?
-- Grão: um piloto com 50 corridas classificadas ou mais.
-- Só corridas em que o piloto foi classificado (posicao não nula) e largou do
-- grid (largada > 0; largada 0 = pit lane, sem posição de largada).
-- media_posicoes_ganhas = média de (largada - posicao); positivo = ganhou.
-- Corte em 50: com poucas corridas a média é ruído.
-- Atenção ao ler: quem larga no fundo tem mais posições a ganhar do que
-- quem larga na frente.
SELECT
    p.id_piloto,
    p.nome || ' ' || p.sobrenome            AS piloto,
    count(*)                                AS corridas_classificadas,
    round(avg(r.largada - r.posicao), 2)    AS media_posicoes_ganhas,
    round(avg(r.largada), 1)                AS largada_media,
    round(avg(r.posicao), 1)                AS chegada_media
FROM refined.resultados AS r
JOIN refined.pilotos    AS p USING (id_piloto)
WHERE r.posicao IS NOT NULL
  AND r.largada > 0
GROUP BY p.id_piloto, piloto
HAVING count(*) >= 50
ORDER BY media_posicoes_ganhas DESC, piloto
