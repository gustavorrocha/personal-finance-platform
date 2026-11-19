# Holdings snapshots

## Accounts

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

## Investments

Open **Investments** (**Investimentos**) and select a connection. The dashboard
shows net balance, gross amount, currency, quantity, unit price, reference date,
maturity date, and UTC observation time. A missing amount appears as unavailable.
Use the reference date to tell when a reported value applies.

Rebuild the local stack and load the invented positions using PowerShell.

```powershell
.\scripts\run_local.ps1
uv run --frozen finance demo-investments
Start-Process 'http://127.0.0.1:8080/#investments'
```

Select **Synthetic demo** if prompted. The BRL demo shows `DEMO11` with a net
balance of 115.20 and a gross amount of 120.25. A fixed-income position has a
gross amount of 800 and an unavailable net balance. Loading the demo again replays
the same observation.

The frontend passed lint, build, and seven tests. Headless Chrome verified both
Investments languages and the Portuguese Accounts view against an isolated
Docker stack seeded with the synthetic fixture.

### Local API

`GET /api/investments` returns the latest reported observation for each position
within a connection. It selects a single connection automatically. When multiple
connections are available, pass a pseudonymous ID from `connections` as `item`.
Each response returns up to 200 positions and includes a `truncated` flag.
Positions with the same ticker stay separate. If a later capture omits a position,
its previous observation can still appear.

The API returns ticker when available in a supported ticker format, type, subtype,
status, currency, net balance, gross amount, quantity, unit price, reference date,
maturity date, and UTC observation time. Monetary and quantity values use decimal
strings. Missing fields stay null. The reference date describes the reported
position value, while the observation timestamp records when ingestion saw it.
The provider defines the balance as net and the amount as gross.
[Investment field definitions](https://docs.pluggy.ai/en/docs/products/investments)

```powershell
Invoke-RestMethod 'http://127.0.0.1:8080/api/investments'
```

All 92 Python tests passed with disposable ClickHouse. Ruff and workflow lint
passed. An isolated Docker build verified the localhost route with a synthetic
position and confirmed that the dashboard role could read the investment view
while ClickHouse denied access to the underlying provider table.
