# Account snapshots

Open **Accounts** (**Contas**) in the dashboard. The view follows the dashboard's
language preference. Select a connection to see each reported balance with its
currency and observation time in UTC.

The localhost API exposes the latest reported account observation per account
and connection at `GET /api/accounts`. A single connection is selected
automatically. When more than one is available, use its pseudonymous ID from
`connections` as the `item` query parameter.

Each row contains a pseudonymous account ID, type, subtype, currency, balance,
and UTC observation time. Balances are decimal strings in the provider's
reported currency and sign. Missing balances remain null. A credit card balance
can represent a liability. The response keeps account rows separate and includes
a `truncated` flag when more than 200 accounts are available for a connection.

Start the local stack to apply the account snapshot migration, then load the
invented balances.

```powershell
.\scripts\run_local.ps1
uv run --frozen finance demo-accounts
Start-Process 'http://127.0.0.1:8080/#accounts'
```

The demo shows BRL 1,850.75 for a bank account, BRL -320.40 for a credit card,
and one USD account with an unavailable balance. Its accounts use the same
synthetic connection as the spending demo. Loading the fixture again replays
the same observation.

The account test also uses two separate synthetic connections that each report
a BRL 42 balance. It verifies exact values, timestamps and scope isolation.
The dashboard service account reads the projection under its existing
file-backed credential.

Validation passed 90 Python tests with disposable ClickHouse and six frontend
tests. A Docker smoke test verified the localhost proxy and restricted grants.
Headless Chrome verified that the Portuguese Accounts view displays the demo
balances and marks the missing USD balance as unavailable.
