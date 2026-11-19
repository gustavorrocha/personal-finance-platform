import english from "./messages.en-US.json" with { type: "json" };
import portuguese from "./messages.pt-BR.json" with { type: "json" };

export type Locale = "en-US" | "pt-BR";
export type LanguagePreference = Locale | "device";

export const LANGUAGE_KEY = "finance-language";

function catalog(copy: typeof english) {
  return {
    ...copy,
    categoryFor: (merchant: string, date: string) =>
      copy.categoryFor.replace(/\{(merchant|date)\}/g, (placeholder) =>
        placeholder === "{merchant}" ? merchant : date,
      ),
  };
}

export const messages = {
  "en-US": catalog(english),
  "pt-BR": catalog(portuguese.messages),
};

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
  currency?: string | null,
): string {
  if (amount === null) return messages[locale].unavailable;
  return new Intl.NumberFormat(locale, {
    ...(currency ? { style: "currency", currency } : {}),
    maximumFractionDigits: 12,
  }).format(amount as Intl.StringNumericLiteral);
}

const investmentTypes = new Map<
  string,
  Exclude<keyof typeof english, "categoryFor">
>(
  Object.entries({
    EQUITY: "investment_EQUITY",
    FIXED_INCOME: "investment_FIXED_INCOME",
    MUTUAL_FUND: "investment_MUTUAL_FUND",
    ETF: "investment_ETF",
    SECURITY: "investment_SECURITY",
  } as const),
);

export function investmentTypeLabel(type: string | null, locale: Locale) {
  const copy = messages[locale];
  if (type === null) return copy.unavailable;
  return copy[investmentTypes.get(type) ?? "investmentOther"];
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
