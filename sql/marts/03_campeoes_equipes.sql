-- Qual equipe foi campeã de construtores em cada ano?
-- Grão: uma temporada com título de construtores (1958 em diante).
-- Mesma regra do campeão de pilotos: posicao 1 na última rodada com
-- classificação publicada.
WITH ultima AS (
    -- Grão: uma temporada.
    SELECT c.ano, arg_max(c.id_corrida, c.rodada) AS id_corrida
    FROM refined.corridas AS c
    SEMI JOIN refined.classificacao_equipes AS ce USING (id_corrida)
    GROUP BY c.ano
),
corridas_ano AS (
    SELECT ano, count(*) AS corridas
    FROM refined.corridas
    GROUP BY ano
)
SELECT
    u.ano,
    e.id_equipe,
    e.nome                        AS equipe,
    e.nacionalidade,
    campea.pontos,
    campea.vitorias,
    ca.corridas,
    campea.pontos - vice.pontos   AS vantagem_pontos
FROM ultima                        AS u
JOIN refined.classificacao_equipes AS campea ON campea.id_corrida = u.id_corrida
                                            AND campea.posicao = 1
JOIN refined.classificacao_equipes AS vice   ON vice.id_corrida = u.id_corrida
                                            AND vice.posicao = 2
JOIN refined.equipes               AS e      ON e.id_equipe = campea.id_equipe
JOIN corridas_ano                  AS ca     ON ca.ano = u.ano
ORDER BY u.ano
