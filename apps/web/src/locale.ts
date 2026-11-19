export type Locale = "en-US" | "pt-BR";
export type LanguagePreference = Locale | "device";

export const LANGUAGE_KEY = "finance-language";

export const messages = {
  "en-US": {
    brand: "Personal Finance",
    workspace: "Local workspace",
    language: "Language",
    deviceLanguage: "Use device language",
    title: "Monthly spending",
    dashboardViews: "Dashboard views",
    spendingView: "Spending",
    accounts: "Accounts",
    account: "Account",
    bankAccount: "Bank account",
    creditCard: "Credit card",
    loadingAccounts: "Loading accounts…",
    accountsError: "Accounts could not be loaded.",
    noAccounts: "No reported accounts are available.",
    reportedBalances: "Reported balances",
    balanceHelp:
      "Balances retain their reported signs and currencies. Credit card balances can represent liabilities.",
    balance: "Balance",
    currency: "Currency",
    observedAt: "Observed (UTC)",
    unavailable: "Unavailable",
    accountLimit: "Showing the first 200 accounts for this connection.",
    accountHistory: "Balance history",
    selectHistoryAccount: "Select an account",
    loadingHistory: "Loading balance history…",
    historyError: "Balance history could not be loaded.",
    noHistory: "No balance observations are available for this account.",
    historyLimit: "Showing the 90 most recent observations.",
    investments: "Investments",
    loadingInvestments: "Loading investments…",
    investmentsError: "Investments could not be loaded.",
    noInvestments: "No reported investments are available.",
    investmentHelp:
      "Each row shows the last reported position. Check its reference date before treating a value as current.",
    investmentLimit: "Showing the first 200 positions for this connection.",
    position: "Position",
    investmentType: "Type",
    netBalance: "Net balance",
    grossAmount: "Gross amount",
    quantity: "Quantity",
    unitPrice: "Unit price",
    referenceDate: "Reference date",
    maturityDate: "Maturity date",
    connection: "Connection",
    syntheticDemo: "Synthetic demo",
    selectConnection: "Select a connection",
    month: "Month",
    year: "Year",
    loading: "Loading expenses…",
    loadError: "Spending could not be loaded.",
    saveError: "The category could not be saved.",
    saved: "Category rule saved.",
    reviewError: "The review decision could not be saved.",
    reviewSaved: "Review decision saved.",
    reviewTitle: "Debit review",
    noReviews: "No debits to review this month.",
    reviewHelp:
      "Include a debit if it was an expense. Unreviewed and excluded debits stay out of spending totals.",
    reviewStatus: "Decision",
    reviewPending: "Needs review",
    reviewIncluded: "Included",
    reviewExcluded: "Excluded",
    reviewAction: "Actions",
    includeExpense: "Include as expense",
    excludeExpense: "Exclude",
    resetReview: "Reset",
    reviewLimit: "Showing up to 100 debits, with unreviewed debits first.",
    reload: "Reload",
    selectForSpending: "Select a connection to view its spending.",
    noExpenses:
      "No expenses are available. Load the synthetic demo or replay a connection.",
    noSpending: "No posted spending for this month.",
    netSpending: "Net spending",
    postedEntry: "posted entry",
    postedEntries: "posted entries",
    awaitingCategory: "Posted entries awaiting a category",
    spendingByCategory: "Spending by category",
    recentExpenses: "Recent expenses",
    matchingExpenses:
      "A category change applies to matching expenses in this connection.",
    date: "Date",
    merchant: "Merchant",
    amount: "Amount",
    category: "Category",
    suggestCategories: "Suggest categories",
    suggesting: "Generating local suggestions…",
    suggestionsReady: "Review the suggestions below before applying them.",
    noSuggestions: "The model had no suggestion for these expenses.",
    suggestionsUnavailable:
      "Local suggestions are unavailable. Check that the Ollama model is installed.",
    suggested: "Suggested",
    applySuggestion: "Apply as merchant rule",
    dismissSuggestion: "Dismiss",
    unknownMerchant: "Unknown merchant",
    expense: "expense",
    categoryFor: (merchant: string, date: string) =>
      `Category for ${merchant} on ${date}`,
    recentLimit: "Showing the most recent 100 entries.",
  },
  "pt-BR": {
    brand: "Finanças Pessoais",
    workspace: "Ambiente local",
    language: "Idioma",
    deviceLanguage: "Usar idioma do dispositivo",
    title: "Gastos mensais",
    dashboardViews: "Seções do painel",
    spendingView: "Gastos",
    accounts: "Contas",
    account: "Conta",
    bankAccount: "Conta bancária",
    creditCard: "Cartão de crédito",
    loadingAccounts: "Carregando contas…",
    accountsError: "Não foi possível carregar as contas.",
    noAccounts: "Nenhuma conta informada está disponível.",
    reportedBalances: "Saldos informados",
    balanceHelp:
      "Os saldos mantêm os sinais e as moedas informados. Saldos de cartão de crédito podem representar dívidas.",
    balance: "Saldo",
    currency: "Moeda",
    observedAt: "Observado (UTC)",
    unavailable: "Indisponível",
    accountLimit: "Exibindo as primeiras 200 contas desta conexão.",
    accountHistory: "Histórico de saldos",
    selectHistoryAccount: "Selecione uma conta",
    loadingHistory: "Carregando histórico de saldos…",
    historyError: "Não foi possível carregar o histórico de saldos.",
    noHistory: "Não há registros de saldo disponíveis para esta conta.",
    historyLimit: "Exibindo os 90 registros mais recentes.",
    investments: "Investimentos",
    loadingInvestments: "Carregando investimentos…",
    investmentsError: "Não foi possível carregar os investimentos.",
    noInvestments: "Nenhum investimento informado está disponível.",
    investmentHelp:
      "Cada linha mostra a última posição informada. Confira a data de referência para saber a que período o valor se refere.",
    investmentLimit: "Exibindo as primeiras 200 posições desta conexão.",
    position: "Posição",
    investmentType: "Tipo",
    netBalance: "Saldo líquido",
    grossAmount: "Valor bruto",
    quantity: "Quantidade",
    unitPrice: "Preço unitário",
    referenceDate: "Data de referência",
    maturityDate: "Vencimento",
    connection: "Conexão",
    syntheticDemo: "Demonstração com dados fictícios",
    selectConnection: "Selecione uma conexão",
    month: "Mês",
    year: "Ano",
    loading: "Carregando despesas…",
    loadError: "Não foi possível carregar os gastos.",
    saveError: "Não foi possível salvar a categoria.",
    saved: "Regra de categoria salva.",
    reviewError: "Não foi possível salvar a decisão da revisão.",
    reviewSaved: "Decisão da revisão salva.",
    reviewTitle: "Revisão de débitos",
    noReviews: "Não há débitos para revisar neste mês.",
    reviewHelp:
      "Inclua um débito se ele for uma despesa. Débitos não revisados ou excluídos ficam fora do total de gastos.",
    reviewStatus: "Decisão",
    reviewPending: "A revisar",
    reviewIncluded: "Incluído",
    reviewExcluded: "Excluído",
    reviewAction: "Ações",
    includeExpense: "Incluir como despesa",
    excludeExpense: "Excluir do total",
    resetReview: "Desfazer decisão",
    reviewLimit: "Exibindo até 100 débitos, com os não revisados primeiro.",
    reload: "Recarregar",
    selectForSpending: "Selecione uma conexão para ver os gastos.",
    noExpenses:
      "Nenhuma despesa disponível. Carregue a demonstração com dados fictícios ou reprocesse os dados de uma conexão.",
    noSpending: "Não há gastos confirmados neste mês.",
    netSpending: "Gasto líquido",
    postedEntry: "lançamento confirmado",
    postedEntries: "lançamentos confirmados",
    awaitingCategory: "Lançamentos confirmados aguardando uma categoria",
    spendingByCategory: "Gastos por categoria",
    recentExpenses: "Despesas recentes",
    matchingExpenses:
      "A mudança de categoria vale para as despesas correspondentes nesta conexão.",
    date: "Data",
    merchant: "Estabelecimento",
    amount: "Valor",
    category: "Categoria",
    suggestCategories: "Sugerir categorias",
    suggesting: "Gerando sugestões locais…",
    suggestionsReady: "Revise as sugestões abaixo antes de aplicar.",
    noSuggestions: "O modelo não encontrou sugestões para essas despesas.",
    suggestionsUnavailable:
      "As sugestões locais estão indisponíveis. Verifique se o modelo está instalado no Ollama.",
    suggested: "Sugestão",
    applySuggestion: "Aplicar como regra",
    dismissSuggestion: "Dispensar",
    unknownMerchant: "Estabelecimento desconhecido",
    expense: "despesa",
    categoryFor: (merchant: string, date: string) =>
      `Categoria de ${merchant} em ${date}`,
    recentLimit: "Exibindo os 100 lançamentos mais recentes.",
  },
};

const brazilianCategories = new Map([
  ["Groceries", "Supermercado"],
  ["Dining", "Alimentação fora de casa"],
  ["Transport", "Transporte"],
  ["Home", "Moradia"],
  ["Shopping", "Compras"],
  ["Health", "Saúde"],
  ["Leisure", "Lazer"],
  ["Uncategorized", "Sem categoria"],
]);

export function categoryLabel(category: string, locale: Locale): string {
  return locale === "pt-BR"
    ? (brazilianCategories.get(category) ?? category)
    : category;
}

export function formatMoney(
  amount: string,
  currency: string,
  locale: Locale,
): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(
    Number(amount),
  );
}

export function formatReportedValue(
  amount: string | null,
  locale: Locale,
): string {
  if (amount === null) return messages[locale].unavailable;
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 12 }).format(
    amount as Intl.StringNumericLiteral,
  );
}

const investmentTypes = new Map<string, [string, string]>([
  ["EQUITY", ["Equity", "Renda variável"]],
  ["FIXED_INCOME", ["Fixed income", "Renda fixa"]],
  ["MUTUAL_FUND", ["Mutual fund", "Fundo de investimento"]],
  ["ETF", ["ETF", "ETF"]],
  ["SECURITY", ["Security", "Valor mobiliário"]],
]);

export function investmentTypeLabel(type: string | null, locale: Locale) {
  if (type === null) return messages[locale].unavailable;
  return locale === "pt-BR"
    ? (investmentTypes.get(type)?.[1] ?? "Outro")
    : (investmentTypes.get(type)?.[0] ?? "Other");
}

export function formatDate(date: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(date));
}

export function monthChoices(locale: Locale) {
  const formatter = new Intl.DateTimeFormat(locale, {
    month: "long",
    timeZone: "UTC",
  });
  return Array.from({ length: 12 }, (_, index) => ({
    value: String(index + 1).padStart(2, "0"),
    label: formatter.format(new Date(Date.UTC(2026, index, 1))),
  }));
}

export function deviceLocale(languages: readonly string[]): Locale {
  for (const language of languages) {
    const base = language.toLowerCase().split("-")[0];
    if (base === "pt") return "pt-BR";
    if (base === "en") return "en-US";
  }
  return "en-US";
}

export function readLanguagePreference(): LanguagePreference {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === "pt-BR" || saved === "en-US") return saved;
  } catch {
    // Changing languages still works when browser storage is disabled.
  }
  return "device";
}
