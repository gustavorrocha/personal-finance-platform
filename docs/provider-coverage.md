# Phase 2 provider coverage audit

The audit queries the existing Pluggy items you specify and prints a redacted JSON
report to the local console. Use an existing Pluggy application and existing
consents. Configure the following environment variables in a private shell session
using your local secret manager. Keep values out of command arguments, shell history,
Git, shared logs, and CI.

| Variable | Value |
|---|---|
| `PLUGGY_CLIENT_ID` | Pluggy application client UUID |
| `PLUGGY_CLIENT_SECRET` | Pluggy application secret |
| `PLUGGY_ITEM_IDS` | JSON array with one or more distinct existing Pluggy item UUIDs |

The list can include multiple items from the same institution or items from
different institutions. The report labels them `item-1`, `item-2`, and so on in
the same order as the list.

```powershell
uv sync --frozen
uv run --frozen finance audit-coverage --redact
```

The only POST is the Pluggy authentication exchange. Subsequent calls are GET reads
against `https://api.pluggy.ai`. The client keeps the token and identifiers in
memory, refuses redirects and cross-account cursors, and uses bounded retries,
page counts, response sizes, and a total request budget. The CLI always redacts
results and requires neither Docker nor the Lake. The audit leaves connection
state, local files, and ClickHouse unchanged.

The report contains generated item labels, connector ID and product declarations,
item status, month-level consent/sync context, resource status counts, and observed
account, card, investment, transaction, bill, and movement counts. Dated collections
include the first and last observed calendar month and the number of dated records.
These are observations of data currently held by Pluggy. They do not establish
continuous history or the institution's total holdings.

| Status | Meaning |
|---|---|
| `observed` | Queried scopes returned one or more rows |
| `empty` | A completed read returned zero rows |
| `no_scope` | No eligible account, card, or investment was observed to query |
| `unavailable` | Pluggy rejected a scope or the requested data was inaccessible |
| `partial` | Some rows or scopes were readable and at least one read was rejected |

An authentication, transport, invalid-response, or page-budget error exits with
an error and omits the report. For individual scope errors, inspect both the
resource's status and upstream scope counts before interpreting totals. The
savings-pot check runs for every item and reports only name-match counts. A `candidate`
needs manual confirmation. `not_observed` only means the audit saw no matching
name. `inconclusive` means coverage was incomplete.

The report omits item/account/transaction IDs, balances, amounts, names,
descriptions, raw dates, credentials, cursors, and provider error bodies. Counts
and date ranges still describe your connections, so keep the report local.

## API references

- [Authentication](https://docs.pluggy.ai/en/reference/auth/auth-create)
- [Item and consent fields](https://docs.pluggy.ai/en/reference/items/items-retrieve)
- [Item resources](https://docs.pluggy.ai/en/reference/items/items-resources)
- [Pagination](https://docs.pluggy.ai/en/reference/basic-concepts)
- [Account paging](https://docs.pluggy.ai/en/reference/account/accounts-list)
- [Transactions by cursor](https://docs.pluggy.ai/en/reference/transaction/transactions-list-by-cursor)
- [Bills](https://v2.docs.pluggy.ai/en/reference/bill/bills-list)
- [Investment movements](https://docs.pluggy.ai/en/reference/investment/investment-transactions-list)

CI uses synthetic HTTP responses. Live coverage verification requires the three
local variables above and an audit against the intended existing consents.
