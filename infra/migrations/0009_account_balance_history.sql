CREATE VIEW IF NOT EXISTS analytics.account_balance_history
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS account_key,
       observed_at,
       tupleElement(observation, 1) AS currency,
       tupleElement(observation, 2) AS balance
FROM
(
    SELECT item_key,
           entity_key,
           observed_at,
           argMax(tuple(currency, balance), tuple(run_id, row_order)) AS observation
    FROM core.provider_observations
    WHERE resource = 'accounts' AND NOT deleted
    GROUP BY item_key, entity_key, observed_at
);
