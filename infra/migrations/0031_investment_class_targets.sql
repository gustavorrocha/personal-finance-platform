-- The share of the portfolio the operator wants in each investment class. Append-only
-- events; the latest per class wins and a zero percent removes the target.
CREATE TABLE IF NOT EXISTS core.investment_class_targets
(
    class_id UUID,
    percent Decimal(7, 4),
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (class_id, changed_at, event_id);

CREATE VIEW IF NOT EXISTS analytics.investment_class_targets
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT class_id, percent
FROM
(
    SELECT class_id, argMax(percent, (changed_at, event_id)) AS percent
    FROM core.investment_class_targets
    GROUP BY class_id
)
WHERE percent > 0 AND class_id IN (SELECT class_id FROM analytics.investment_classes);
