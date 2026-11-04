-- Quem foi o campeão de pilotos de cada ano?
-- Grão: uma temporada.
-- Campeão = posicao 1 na classificação da última rodada do ano que tem
-- classificação publicada. Pontos são os daquele ano, no sistema daquele ano.
WITH ultima AS (
    -- Grão: uma temporada.
    SELECT c.ano, arg_max(c.id_corrida, c.rodada) AS id_corrida
    FROM refined.corridas AS c
    SEMI JOIN refined.classificacao_pilotos AS cp USING (id_corrida)
    GROUP BY c.ano
),
corridas_ano AS (
    SELECT ano, count(*) AS corridas
    FROM refined.corridas
    GROUP BY ano
)
SELECT
    u.ano,
    p.id_piloto,
    p.nome || ' ' || p.sobrenome   AS piloto,
    p.nacionalidade,
    campeao.pontos,
    campeao.vitorias,
    ca.corridas,
    campeao.pontos - vice.pontos   AS vantagem_pontos
FROM ultima                        AS u
JOIN refined.classificacao_pilotos AS campeao ON campeao.id_corrida = u.id_corrida
                                             AND campeao.posicao = 1
JOIN refined.classificacao_pilotos AS vice    ON vice.id_corrida = u.id_corrida
                                             AND vice.posicao = 2
JOIN refined.pilotos               AS p       ON p.id_piloto = campeao.id_piloto
JOIN corridas_ano                  AS ca      ON ca.ano = u.ano
ORDER BY u.ano
