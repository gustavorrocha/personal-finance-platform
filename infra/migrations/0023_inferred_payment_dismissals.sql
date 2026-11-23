-- Suggested savings-box payments the operator ignored, so they are not suggested again.
CREATE TABLE IF NOT EXISTS core.inferred_payment_dismissals
(
    cnpj String,
    month Date,
    dismissed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (cnpj, month, dismissed_at, event_id);

CREATE VIEW IF NOT EXISTS analytics.inferred_payment_dismissals
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT DISTINCT cnpj, formatDateTime(month, '%Y-%m') AS month
FROM core.inferred_payment_dismissals;
