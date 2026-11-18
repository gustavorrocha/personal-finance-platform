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
    connection: "Connection",
    syntheticDemo: "Synthetic demo",
    selectConnection: "Select a connection",
    month: "Month",
    year: "Year",
    loading: "Loading expenses…",
    loadError: "Spending could not be loaded.",
    saveError: "The category could not be saved.",
    saved: "Category rule saved.",
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
    connection: "Conexão",
    syntheticDemo: "Demonstração com dados fictícios",
    selectConnection: "Selecione uma conexão",
    month: "Mês",
    year: "Ano",
    loading: "Carregando despesas…",
    loadError: "Não foi possível carregar os gastos.",
    saveError: "Não foi possível salvar a categoria.",
    saved: "Regra de categoria salva.",
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
