import {
  formatDate,
  formatReportedValue,
  messages,
  type Locale,
} from "./locale";

export type TransactionDetails = {
  description?: string;
  bank_category?: string;
  transaction_time?: string | null;
  original_purchase_date?: string | null;
  installment_number?: number | null;
  total_installments?: number | null;
  installment_total_amount?: string | null;
  mcc?: number | null;
  cnpj?: string;
  cnae?: string;
  business_name?: string;
  merchant_category?: string;
};

function formatCnpj(value: string) {
  return value.replace(
    /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,
    "$1.$2.$3/$4-$5",
  );
}

export function TransactionDetailCell({
  entry,
  locale,
  connection,
}: {
  entry: TransactionDetails & {
    merchant: string;
    currency: string;
    operation?: string;
  };
  locale: Locale;
  connection?: string;
}) {
  const copy = messages[locale];
  const description = entry.description?.trim()
    ? entry.description
    : entry.merchant;
  const format = new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  });
  return (
    <td className="transaction-details">
      <div>{description || entry.operation || copy.unavailable}</div>
      {entry.merchant && description !== entry.merchant && (
        <small>{entry.merchant}</small>
      )}
      {entry.business_name && entry.business_name !== entry.merchant && (
        <small>{entry.business_name}</small>
      )}
      {(entry.cnpj || entry.mcc || entry.merchant_category) && (
        <small>
          {[
            entry.cnpj && `${copy.cnpj} ${formatCnpj(entry.cnpj)}`,
            entry.merchant_category,
            entry.cnae && `${copy.cnae} ${entry.cnae}`,
            entry.mcc && `${copy.mcc} ${entry.mcc}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </small>
      )}
      {connection && <small>{connection}</small>}
      {entry.transaction_time && (
        <small>
          {copy.reportedTime}{" "}
          <time dateTime={entry.transaction_time}>
            {format.format(new Date(entry.transaction_time))}
          </time>
        </small>
      )}
      {entry.original_purchase_date && (
        <small>
          {copy.originalPurchaseDate}{" "}
          {formatDate(entry.original_purchase_date, locale)}
        </small>
      )}
      {(entry.installment_number || entry.total_installments) && (
        <small>
          {copy.installment} {entry.installment_number ?? copy.unavailable}
          {entry.total_installments && (
            <>
              {" / "}
              {entry.total_installments}
            </>
          )}
        </small>
      )}
      {entry.installment_total_amount != null && (
        <small>
          {copy.installmentTotal}{" "}
          {formatReportedValue(
            entry.installment_total_amount,
            locale,
            entry.currency,
          )}
        </small>
      )}
    </td>
  );
}
