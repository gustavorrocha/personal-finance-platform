# Private spending dashboard

Run the [synthetic demo](../README.md#try-the-spending-dashboard) to browse net
spending by month, connection and currency. Category changes save a rule for the
matching merchant in that connection. Selecting **Uncategorized** explicitly puts
matching purchases back in the review list. Replay preserves these rule events.

## What counts as spending

- Count posted debit transactions with card-account, card metadata, or recognized
  spending-category evidence. Subtract posted credits with explicit refund evidence.
- Exclude recognized transfers, card payments, cashback and pending transactions.
  Ambiguous debits and credits stay in the imported history for later reconciliation.
- Resolve the latest transaction before grouping. Keep one connection selected.
  A reconnect can retain overlapping history under a separate connection.
- Group totals by currency before reporting. The table displays up to 100 recent
  entries while category and monthly totals cover the whole selected month.

The classifier maps recognized source categories and a few structured merchant
keywords to a short list. The local operator can override these suggestions.
Rule matching uses a fingerprint of normalized
merchant text, with an individual transaction fallback for records lacking a
usable label. The dashboard shows only structured merchant names when available.
Raw provider descriptions remain in private Bronze. [Pluggy transaction fields](https://docs.pluggy.ai/en/reference/transaction/transactions-retrieve)

## Existing imported data

Startup provisions the local dashboard credential and applies migration 0005.
Replay previously imported provider runs to populate the new spending evidence.
Use the regular offline rebuild command to replay every committed capture.

```powershell
uv run --frozen finance rebuild-warehouse --from-bronze
```

The ClickHouse dashboard user can select the spending projection and insert rule
events. Its file-backed password is available to the API only. Category updates
require a local browser origin. Before using personal data, verify an independent
backup of Bronze and `core.spending_rules`. The existing foundation backup covers
the synthetic probe table.

To inspect the ClickHouse model from the local operator shell, compare the
spending projection with `core.bank_transaction_current`. The spending view picks
one transaction version before applying settlement filters, review rules and
currency totals. This preserves stable aggregates while ClickHouse merges table
parts in the background.

## Validation

82 Python tests passed, including the synthetic ClickHouse tests for monthly
totals, correction propagation and replay. Ruff and the frontend lint, tests and
build passed. A disposable Docker stack verified that the dashboard account
can read the spending view while access to the source rows and rule history is
denied. A hostile Host header was rejected, and a synthetic rule survived a
container restart. Headless Chrome rendered the demo total. Live-data validation
and independent backup recovery remain pending.
