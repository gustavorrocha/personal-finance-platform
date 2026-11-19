# Private spending dashboard

Run the [synthetic demo](../README.md#try-the-spending-dashboard) to browse net
spending by month, connection and currency. Category changes save a rule for the
matching merchant in that connection. Selecting **Uncategorized** explicitly puts
matching purchases back in the review list. Replay preserves these rule events.

The dashboard follows the browser's preferred language by default and falls
back to English. Use **Language** in the header to choose **English** or
**Português (Brasil)**, or select **Use device language** to clear a saved choice.
Explicit choices are stored locally in the browser. Category
labels, dates and amounts are displayed in the chosen language, and both modes
use the same saved rules and transaction currency.

## What counts as spending

- Count posted debit transactions with card-account, card metadata, or recognized
  spending-category evidence. Subtract posted credits with explicit refund evidence.
- Exclude recognized transfers, card payments, cashback and pending transactions.
  Posted debits with ambiguous evidence appear in **Debit review**. A payment-method
  label such as PIX alone leaves the debit for review. Ambiguous credits stay in
  the imported history. [Pluggy transaction fields](https://docs.pluggy.ai/en/reference/transaction/transactions-retrieve)
- Resolve the latest transaction before grouping. Keep one connection selected.
  A reconnect can retain overlapping history under a separate connection.
- Group totals by currency before reporting. The table displays up to 100 recent
  entries while category and monthly totals cover the whole selected month.

The classifier maps recognized source categories and a few structured merchant
keywords to a short list. The local operator can override these suggestions.
Rule matching uses a fingerprint of normalized
merchant text, with an individual transaction fallback for records lacking a
usable label. The dashboard shows the bank description when available, with
the structured merchant name as a fallback. Raw payloads remain in private Bronze.

## Review a debit

Find **Debit review** directly below the monthly totals. Choose **Include as
expense** to add one debit to the monthly total. Set its
category afterwards in **Recent expenses**. **Exclude** leaves it out of totals
and records the decision. **Reset** returns to the automatic result. The review
table shows up to 100 debits, with unreviewed ones first.

Review decisions apply to a single transaction within a connection. They survive
Bronze replay and cannot reinstate a deleted or pending transaction or a recognized
transfer. The synthetic Harbor Books debit adds BRL 23.50 when included.

## Existing imported data

Startup provisions the local dashboard credential and applies the spending and
review migrations. Replay previously imported provider runs to populate the new
review evidence.
Use the regular offline rebuild command to replay every committed capture.

```powershell
uv run --frozen finance rebuild-warehouse --from-bronze
```

The ClickHouse dashboard user can select the spending projection and insert rule
and review events. Its file-backed password is available to the API only. Category
and review updates require a local browser origin. Before using personal data,
verify an independent backup of Bronze, `core.spending_rules`, and
`core.spending_reviews`. The existing foundation backup covers
the synthetic probe table.

To inspect the ClickHouse model from the local operator shell, compare the
spending projection `analytics.spending_dashboard` with `core.bank_transaction_current`.
The spending dashboard view picks
one transaction version before applying settlement filters, review rules and
currency totals. This preserves stable aggregates while ClickHouse merges table
parts in the background.

## Validation

83 Python tests passed, including the synthetic ClickHouse tests for monthly
totals, correction propagation, cross-connection review rejection and replay.
Ruff and the frontend lint, tests and build passed. A disposable Docker stack
verified review and reset through the dashboard API and denied the service
account access to raw transaction rows and review history. Headless Chrome
rendered the Portuguese review panel. Live-data validation and independent
backup recovery remain pending.

## Spending across connections

Spending opens on **All imported connections** when imported data is available.
Choose a connection to narrow the same monthly view. Synthetic demo data stays
out of the combined totals and is hidden from selectors when imported
connections are available. Totals are grouped by currency. Category edits,
local suggestions, and debit review decisions use the transaction's own
connection.

Totals include posted credit-card purchases and bank debits with purchase
evidence, such as a debit-card operation or a recognized spending category.
Known transfers and card bill payments are excluded. Ambiguous debits such as
PIX remain in Debit review until included. The review shows a recognized
payment method when neither a bank description nor a merchant is available.

**Pending card spending** shows purchases dated in the selected month that
the provider still marks pending. They move into posted spending when a newer
observation settles the same transaction. A positive card debit reported with
card metadata can count as a purchase even when its operation code is
`PAGAMENTO`. Explicit bill payments stay excluded.
[Pluggy transaction statuses and direction](https://docs.pluggy.ai/en/docs/products/transactions)

The monthly expense list displays posted and pending purchases. Search the
bank description, merchant, or category across all pages without changing the
monthly totals. The bank description and category remain in the original
language. When present, the list shows the reported transaction time in UTC,
original purchase date, installment number and count, and total purchase amount.
Date-only and midnight timestamps are shown without an inferred time of payment.
Transaction descriptions stay local and are excluded from both Ollama suggestions
and interface translation.

For data imported before the payment-method field was added, rebuild the local
projections from existing captures after applying the migrations. This uses the
existing local data and does not contact Pluggy.

```powershell
.\scripts\run_local.ps1
uv run --frozen finance rebuild-warehouse --from-bronze
```
