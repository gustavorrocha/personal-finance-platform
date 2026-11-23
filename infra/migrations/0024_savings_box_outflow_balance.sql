-- Expose the balance before each savings-box drop, so the API can remove the yield it
-- earned in between and estimate the bill paid at full value.
CREATE OR REPLACE VIEW analytics.savings_box_outflows
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
WITH boxes AS
(
    SELECT DISTINCT item_key, box_key, account_key, lower(name) AS box, currency
    FROM analytics.savings_box_history
),
events AS
(
    SELECT item_key, box_key, observed_on AS day, 1 AS observation, balance,
           toDecimal128(0, 12) AS flow, name
    FROM analytics.savings_box_history
    UNION ALL
    SELECT b.item_key, b.box_key, f.day, 0, NULL, f.flow, ''
    FROM
    (
        SELECT item_key, lower(savings_box) AS box, economic_date AS day,
               toDecimal128(sum(if(kind = 'contribution', amount, -amount)), 12) AS flow
        FROM analytics.investment_flows
        WHERE savings_box != ''
        GROUP BY item_key, box, day
    ) AS f
    INNER JOIN boxes AS b ON f.item_key = b.item_key AND f.box = b.box
),
running AS
(
    SELECT *,
           sum(flow) OVER (PARTITION BY box_key ORDER BY day, observation
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative
    FROM events
),
observed AS
(
    SELECT item_key, box_key, name, day, balance, cumulative,
           lagInFrame(balance) OVER w AS previous_balance,
           lagInFrame(cumulative) OVER w AS previous_cumulative,
           lagInFrame(day) OVER w AS previous_day,
           row_number() OVER w AS position
    FROM running
    WHERE observation = 1
    WINDOW w AS (PARTITION BY box_key ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT o.item_key AS item_key,
       o.box_key AS box_key,
       reinterpretAsUUID(MD5(concat('savings-box-outflow:', toString(o.box_key), ':', toString(o.day)))) AS transaction_key,
       o.name AS name,
       b.currency AS currency,
       o.previous_day AS previous_day,
       o.day AS economic_date,
       o.previous_balance + (o.cumulative - o.previous_cumulative) - o.balance AS amount,
       o.previous_balance AS previous_balance
FROM observed AS o
INNER JOIN boxes AS b ON o.box_key = b.box_key
WHERE o.position > 1 AND amount >= 1;
