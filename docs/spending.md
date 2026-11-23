# Private spending dashboard

Run the [synthetic demo](../README.md#try-the-spending-dashboard) to browse net
spending by month, connection and currency. Categories have two levels and are
edited under **Categories**; see [Categories](#categories).

The dashboard follows the browser's preferred language by default and falls
back to English. Use **Language** in the header to choose **English** or
**Português (Brasil)**, or select **Use device language** to clear a saved choice.
Explicit choices are stored locally in the browser. Category
labels, dates and amounts are displayed in the chosen language, and both modes
use the same saved rules and transaction currency.

## What counts as spending

- Count posted debit transactions with card-account, card metadata, or recognized
  spending-category evidence. The bank's consumption category (services, digital
  services, housing, utilities, food, transport, health, travel, shopping,
  leisure and fees) counts even for PIX and boleto payments, such as bills paid
  from a Mercado Pago savings box. Subtract posted credits with explicit refund
  evidence.
- Exclude card bill payments, transfers between own accounts, savings-box and
  other investment movements, cashback and pending transactions. A debit whose
  only evidence is a generic transfer category, such as a PIX to a person or a
  boleto filed as a transfer, appears in **Debit review**. A payment-method label
  such as PIX alone also leaves the debit for review. Ambiguous credits stay in
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

**Debit review** sits at the top of the spending page and lists pending debits
from every month: it is a backlog, not a monthly view. Choose **Include as
expense** to count a debit in its month, or **Exclude** to leave it out. A
decided debit leaves the list and moves to **Reviewed debits**, collapsed below,
where **Reset** returns it to the automatic result. Set the category of an
included debit in **Recent expenses**. The review shows up to 100 debits.

Review decisions apply to a single transaction within a connection. They survive
Bronze replay and cannot reinstate a deleted or pending transaction or a recognized
transfer. The synthetic Harbor Books debit adds BRL 23.50 when included.

## Spending the bank does not report

Mercado Pago does not report payments made straight from a savings-box balance,
such as a boleto paid with the money in a box; only the box balance drops.

- **Savings-box outflows.** Each sync keeps every box balance. When a balance
  falls by more than the reported withdrawals since the previous observation
  (`balance before + contributions - withdrawals - balance after`, at least
  1.00), the difference appears in **Debit review** as "Left a savings box
  without a reported transaction", dated on the later observation. Detection
  starts with the first stored balance (2026-11-19); earlier months cannot be
  reconstructed. A category set with **This merchant** applies to every outflow
  of that box.
- **Manual and recurring entries.** Under **Manual and recurring entries**, add
  an expense with its connection, amount, day, category and start month. A
  recurring entry repeats every month until its end month or until today. With
  the payee's CNPJ, a month that already has a reported payment to that CNPJ
  skips the entry, so a bill paid sometimes from the account and sometimes from
  a box counts once. Do not also include a box outflow for a bill that a manual
  entry already covers.

A manual entry can name the savings box that paid it (**Paid from savings
box**). Each occurrence then counts as a withdrawal from that box, so the
outflow is not reported again and the box's past balances are estimated
correctly.

**Transfers received** lists the month's PIX, TED and DOC credits from other
people (not between own accounts, not income or investments). **Count as
refund** subtracts one from spending, such as a friend's share of a dinner, and
asks for its subcategory; **Not a refund** hides it among the decided ones.

**Likely paid from a savings box** turns money that left a box into suggested
payments. The evidence is always a box balance falling without a reported
withdrawal:

- **Observed:** since the box's first stored balance, each drop between two
  syncs is the previous balance plus reported contributions, minus reported
  withdrawals, plus the yield expected over those days, minus the new balance.
  Providers report only the current balance, so one sync a day gives a one-day
  window. It is suggested when a
  monthly bill (same CNPJ, stable amount) fits that amount (within 10% of its
  observed range) and its usual day falls between the syncs; other drops stay in
  **Debit review**.
- **Estimated:** before the first stored balance only the total that left is
  known (yield removed, at the rate implied by a box whose balance only grew).
  A monthly bill missing from a month inside the period in which it was paid is
  suggested only if the box keeps enough money, with yield, for every later
  reported withdrawal and suggested payment, and only up to that total.

**Accept** opens the prefilled payment (description, amount, date, category,
box, CNPJ) for editing and records it as a manual entry paid from the box;
**Ignore** stores the decision in `core.inferred_payment_dismissals`.

Manual entries are append-only events in `core.manual_expenses`. Outflows are
computed by `analytics.savings_box_outflows`.

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
verify an independent backup of Bronze, `core.spending_categories`,
`core.category_rules`, and
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
connections are available. Totals are grouped by currency. Local suggestions
and debit review decisions use the transaction's own connection; category rules
apply across connections.

Totals include posted credit-card purchases and bank debits with purchase
evidence, such as a debit-card operation or a recognized spending category.
Known transfers and card bill payments are excluded. Ambiguous debits such as
PIX remain in Debit review until included. The review shows a recognized
payment method when neither a bank description nor a merchant is available.

**Spending this month** adds account debits, posted card purchases and pending
card purchases for each currency, and compares the total with the previous month.
**Monthly comparison** charts the same split for the last 12 months; select a
month to open it, or show the figures as a table. **Categories vs. previous
month** groups subcategories under their category and compares each with the
month before. Select a category or subcategory to list that month's expenses
in it. **Recent expenses** shows the latest 10; **Show more** opens the full,
searchable list.

**Invested wealth over time** stacks, for each of the last 12 months, the
invested money of each investment class, valued day by day. Providers report
only current balances, so each sync stores the balance of every position and
savings box of that day, gross of the income tax and IOF withheld on redemption.
Investment balances count for the day before they were observed, as providers
report the previous close. Other days walk from the nearest stored balance
through the purchases and sales reported for each position (contributions and
withdrawals for a savings box) and, for positions that follow a curve, its daily
yield on business days: the CDI or Selic times the contracted percentage
(savings boxes included), or the contracted fixed rate over 252 business days
for CDBs, LCAs and LCIs. Tesouro Direto bonds follow the morning redemption
price the Tesouro publishes (PU Venda Manhã), matched by title and due date, so
they are marked to market; on the purchase day they show about 1% less than
paid, the spread between buying and redemption prices. Funds follow their quota
in the CVM daily report (matched by CNPJ; subclasses are skipped as ambiguous)
and stocks and ETFs their B3 closing price (matched by ticker; dividends arrive
as account transactions, not in the position). A position without a curve or a
price shows money put in on those days rather than market value. A position that received more than it holds and returned lost the
rest without a reported withdrawal, such as a bill paid straight from a savings
box; the chart warns about it and draws it at zero where the estimate would be
negative, until those payments are registered as manual entries paid from the
box.

**Investment returns** shows time-weighted returns, gross of income tax, of
the portfolio, each class and each held position (BRL) for the month, 3, 6 and
12 months and the year, up to yesterday, next to the CDI and a 12-month
cumulative chart. A position's daily return comes from its model (its rate
curve or public price), not from changes in its balance, so contributions,
withdrawals and payments made straight from a savings box are neither gains
nor losses; a Tesouro coupon payment counts as earned instead of as the price
drop it causes. A class or the portfolio averages its positions weighted by the
previous day's value. Positions without a rate or public price are left out and
listed below the table. A position held for less than a period shows its return
since it was bought, and every row's share of the CDI compares it with the CDI
compounded over the days that row was held. The chart draws the cumulative
12-month return of the portfolio, the CDI and each class (classes in the same
colors and order as the invested wealth chart; end labels only up to four
lines, the tooltip and table always).

`finance market-sync` downloads the last ten years of the public CDI, Selic and
IPCA series from the Banco Central (SGS) into `core.market_rates`, and of every
Tesouro Direto bond's prices from the Tesouro Transparente into
`core.market_prices`, together with the last 13 months of the CVM daily fund
report and B3 historical quotes, keeping only the funds and tickers held. Those
are monthly or daily files for the whole market, never anything tied to a
holding. `core.market_downloads` remembers the files already read for the
current set of holdings, so later runs fetch only new files (and the CVM's last
two months, which it still revises); buying a new fund or ticker fetches its
history again.

One source is asked by name: a held ticker with no price in B3's files over the
last 30 days (an ETF B3 leaves out of its historical files) gets its daily
closes from Yahoo Finance's chart endpoint, the one `yfinance` reads, so Yahoo
sees that ticker. It is not an official API and may change or refuse requests;
a ticker that fails keeps showing money put in, and the rest of the sync goes
on. Only closed days are stored (never the bar still trading), and later runs
ask only for the days after the last one stored. The synthetic demo connection
is never looked up. Run it after a sync; days
without a published rate yet reuse the latest one.

**Investment classes** (on the **Categories** page) start as Renda fixa -
Inflação, Renda fixa - CDI, Renda fixa - Pré, Cotas de fundos, ETF renda fixa
and ETF ações. Each position gets an automatic class: savings boxes and CDI or
Selic indexers are CDI, IPCA, IGP-M and INPC are inflation, other fixed income
is prefixed, mutual funds are fund shares and equities are stock ETFs. Choose
another class for a position, or create, rename and delete classes; a position
in a deleted class returns to its automatic class, or to unclassified.

Card purchases count in
the month of their transaction date, not the month of their bill.

**Net invested** shows, for the same month, contributions minus withdrawals,
with investment income (yields, coupons, net of investment taxes) apart.
**Investments by month** charts the net amount for the last 12 months. Money
moved into investments is never counted as spending. A posted account
transaction counts as an investment movement when:

- its description starts with `Dinheiro reservado` (contribution) or
  `Dinheiro retirado` (withdrawal), as Mercado Pago reports savings boxes
  ("caixinhas"), which have no separate investment positions;
- its description starts with a fixed-income movement such as
  `COMPRA - CDB`, `VENCIMENTO - LCA` or `CUPOM - CDB`; or
- its provider category is an investment category (debits contribute, credits
  withdraw), or `Proceeds interests and dividends` / `Taxes on investments`
  (income).

**Total invested** shows the latest reported balances, whatever the selected
month: investment positions plus money reserved inside bank accounts. Mercado
Pago reports savings boxes as reserved balances of the checking account
(`bankData.reservedBalances`), in the account currency.

Each savings box is also kept on its own. **Investments** lists every box of
the selected connection with its balance and remuneration (for example
`120% CDI`) next to the reported positions. For return calculations, the
warehouse keeps:

| View | Content |
|---|---|
| `analytics.savings_boxes` | Boxes in the latest observation of each account: name, currency, balance, indexer and percentage, fixed rate |
| `analytics.savings_box_history` | One balance per box and observation day |
| `analytics.investment_flows` | Investment movements; `savings_box` names the box of a `Dinheiro reservado/retirado` movement |

Investment positions also keep their name, issuer, purchase date, fixed annual
rate, original and withdrawable amounts, income tax and IOF. Investment
movements keep their direction, net amount, income tax, IOF and the sum of
brokerage, custody, exchange and other fees. These columns live in
`core.provider_versions`.

Transactions keep the merchant's reported identity: CNPJ, CNAE, business name
and activity, the card MCC, and the provider category code. When a transfer
goes to or comes from a company, its CNPJ and name identify the merchant.
Personal documents and names of people stay in Bronze. A transfer whose other
side has the same CPF as an account holder of that connection is a transfer
between own accounts: it is never spending and appears in
`analytics.own_transfers`.

Card transactions are never investment movements. Rebuild the projections from
Bronze after applying the migrations to classify earlier imports.

Pending card purchases are purchases dated in the selected month that
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

## Categories

Categories have two levels, such as **Alimentação** › **Delivery**. Every name
is editable under **Categories**: rename, add, move a subcategory to another
category or make it a category, and archive. Archiving hides the category and
its subcategories; their expenses return to automatic classification. An
expense can belong to a category directly or to one of its subcategories.

Each expense takes the first match of:

1. a rule for that single transaction, such as one PIX to a person;
2. a rule for its merchant;
3. a rule for its specific provider category, such as `Food delivery`;
4. a rule for its card MCC, such as 5812 for restaurants;
5. a rule for its provider category group, such as `Groceries`.

A specific provider category wins over the MCC because an MCC describes the
merchant, not the purchase: food delivery is billed under the restaurant's MCC.
A broad provider category loses to the MCC, which corrects restaurants filed as
groceries. In **Recent expenses**, choose a category and where it applies: **This
merchant**, **Only this transaction**, **Every card purchase with MCC**, or
**Every expense in the bank category**. PIX, TED and DOC transfers and refunds
default to **Only this transaction**. **Automatic (rules)** removes the rule at that level. The expense
shows which rule classified it.

The initial categories and the provider category and MCC rules were seeded on
2026-11-19 (`infra/migrations/0018_spending_categories.sql`). Earlier per-connection
merchant rules in `core.spending_rules` are kept but no longer applied.
Categories and rules are append-only events in `core.spending_categories` and
`core.category_rules`. The spending views read the current rules from the
in-memory dictionary `core.category_rule_dict`, which the API reloads after
every change.
