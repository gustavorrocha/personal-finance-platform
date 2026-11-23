-- A savings box earns its CDI share between two stored balances, which hides part of any
-- payment made straight from it, and can hide a small payment entirely. The outflow is now
-- what is missing from the expected balance: the previous balance grown by the CDI times
-- the box's percentage on the business days in between, plus reported contributions, minus
-- reported withdrawals. (1 + CDI * share) is taken as (1 + CDI) ^ share, which differs by
-- under a millionth a day. Days after the last published CDI earn nothing yet.
--
-- Transactions carry a date but no time, so a contribution or withdrawal on the day of a
-- stored balance may have happened before or after it was read. Each side's same-day
-- movements count in whichever order leaves the least unexplained (and only money still in
-- the box earns yield).
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
           toDecimal128(0, 12) AS flow, name,
           if(indexer = 'CDI', toFloat64(ifNull(indexer_percentage, 0)) / 100, 0) AS share
    FROM analytics.savings_box_history
    UNION ALL
    SELECT b.item_key, b.box_key, f.day, 0, NULL, f.flow, '', 0
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
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative,
           sum(flow) OVER (PARTITION BY box_key, day) AS day_flow
    FROM events
),
-- Log of the CDI index through each business day: the yield of a day accrues to the next.
cdi AS
(
    SELECT 1 AS calendar, day AS rate_day,
           sum(log(1 + toFloat64(value) / 100)) OVER (ORDER BY day
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS level
    FROM analytics.market_rates
    WHERE series = 'CDI'
),
observations AS
(
    SELECT r.*, ifNull(c.level, 0) AS level
    FROM (SELECT *, 1 AS calendar FROM running WHERE observation = 1) AS r
    ASOF LEFT JOIN cdi AS c ON r.calendar = c.calendar AND r.day > c.rate_day
),
observed AS
(
    SELECT item_key, box_key, name, day, balance, cumulative, day_flow, share, level,
           lagInFrame(balance) OVER w AS previous_balance,
           lagInFrame(cumulative) OVER w AS previous_cumulative,
           lagInFrame(day_flow) OVER w AS previous_day_flow,
           lagInFrame(level) OVER w AS previous_level,
           lagInFrame(day) OVER w AS previous_day,
           row_number() OVER w AS position
    FROM observations
    WINDOW w AS (PARTITION BY box_key ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
candidates AS
(
    SELECT *,
           toDecimal128(exp(share * (level - previous_level)) - 1, 12) AS growth,
           -- Movements strictly between the two days.
           cumulative - day_flow - previous_cumulative AS between,
           -- (yield, missing) when the previous day's movements came after (or before) its
           -- stored balance, and the current day's before (or after) its own.
           arrayMap(
               option -> (
                   (previous_balance + if(option.1, previous_day_flow, 0)) * growth,
                   (previous_balance + if(option.1, previous_day_flow, 0)) * (1 + growth)
                       + between + if(option.2, day_flow, 0) - balance
               ),
               [(false, true), (true, true), (true, false), (false, false)]
           ) AS options,
           arraySort(option -> abs(option.2), options)[1] AS best
    FROM observed
    WHERE position > 1
)
SELECT o.item_key AS item_key,
       o.box_key AS box_key,
       reinterpretAsUUID(MD5(concat('savings-box-outflow:', toString(o.box_key), ':', toString(o.day)))) AS transaction_key,
       o.name AS name,
       b.currency AS currency,
       o.previous_day AS previous_day,
       o.day AS economic_date,
       o.best.1 AS expected_yield,
       o.best.2 AS amount,
       o.previous_balance AS previous_balance
FROM candidates AS o
INNER JOIN boxes AS b ON o.box_key = b.box_key
WHERE amount >= 1;
