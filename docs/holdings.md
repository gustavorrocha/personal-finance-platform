# Account snapshots

The localhost API exposes the latest reported account observation per account
and connection at `GET /api/accounts`. A single connection is selected
automatically. When more than one is available, use its pseudonymous ID from
`connections` as the `item` query parameter.

Each row contains a pseudonymous account ID, type, subtype, currency, balance,
and UTC observation time. Balances are decimal strings in the provider's
reported currency and sign. Missing balances remain null. A credit card balance
can represent a liability. The response keeps account rows separate and includes
a `truncated` flag when more than 200 accounts are available for a connection.

Start the normally configured local stack to apply the account snapshot
migration. Fetch the endpoint from the dashboard's localhost port.

```powershell
.\scripts\run_local.ps1
$accounts = Invoke-RestMethod 'http://127.0.0.1:8080/api/accounts'
$accounts.accounts
```

The synthetic spending demo can show missing balances because its fixtures have
no reported balances. The account test uses two separate synthetic connections
that each report a BRL 42 balance. It verifies exact values, timestamps and
scope isolation. The dashboard service account reads the new projection under
its existing file-backed credential.

Validation passed 85 Python tests with disposable ClickHouse. A separate Docker
smoke test verified the localhost proxy, null balances, and denial of direct
provider-table reads by the dashboard account.
