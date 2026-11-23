import { useState, type FormEvent } from "react";
import { categoryPath, categoryTree, type CategoryNode } from "./categories";
import { formatDate, formatMoney, messages, type Locale } from "./locale";
import {
  TransactionDetailCell,
  type TransactionDetails,
} from "./transaction-details";
import { Dialog } from "./ui";

export type RuleScope = "transaction" | "merchant" | "mcc" | "provider";

// Transfers rarely say what they paid for: classify each one on its own by default.
const TRANSFER_RAILS = ["PIX", "TED", "DOC"];

export type DialogExpense = TransactionDetails & {
  id: string;
  item: string;
  date: string;
  currency: string;
  amount: string;
  merchant: string;
  operation?: string;
  status?: "POSTED" | "PENDING";
  category?: string;
  subcategory?: string;
  category_id?: string;
  category_rule?:
    "" | "transaction" | "merchant" | "mcc" | "provider" | "manual";
  provider_category_id?: string;
};

/** Every reported detail of one expense, and where to change its category. */
export function ExpenseDialog({
  entry,
  editable,
  categories,
  locale,
  connection,
  saving,
  suggestion,
  onSave,
  onDismissSuggestion,
  onClose,
}: {
  entry?: DialogExpense;
  editable: boolean;
  categories: CategoryNode[];
  locale: Locale;
  connection?: string;
  saving: boolean;
  suggestion?: string;
  onSave: (category: string | null, scope: RuleScope) => void;
  onDismissSuggestion: () => void;
  onClose: () => void;
}) {
  const copy = messages[locale];
  const [scope, setScope] = useState<RuleScope>(() =>
    entry &&
    (TRANSFER_RAILS.includes(entry.operation ?? "") || Number(entry.amount) < 0)
      ? "transaction"
      : "merchant",
  );
  const tree = categoryTree(categories);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const category = String(
      new FormData(event.currentTarget).get("category") ?? "",
    );
    onSave(category || null, scope);
  }

  const scopes: { value: RuleScope; label: string; available: boolean }[] =
    entry
      ? [
          {
            value: "transaction",
            label: copy.scopeTransaction,
            available: true,
          },
          { value: "merchant", label: copy.scopeMerchant, available: true },
          {
            value: "mcc",
            label: `${copy.scopeMcc} ${entry.mcc ?? ""}`,
            available: entry.mcc != null,
          },
          {
            value: "provider",
            label: `${copy.scopeProvider}: ${entry.bank_category || entry.provider_category_id}`,
            available: Boolean(entry.provider_category_id),
          },
        ]
      : [];

  return (
    <Dialog
      open={Boolean(entry)}
      title={copy.expenseDetails}
      closeLabel={copy.close}
      onClose={() => {
        setScope("merchant");
        onClose();
      }}
    >
      {entry && (
        <>
          <p className="dialog-amount">
            <strong>{formatMoney(entry.amount, entry.currency, locale)}</strong>
            <span>
              <time dateTime={entry.date}>
                {formatDate(entry.date, locale)}
              </time>
              {" · "}
              {entry.status === "PENDING"
                ? copy.pendingStatus
                : copy.postedStatus}
            </span>
          </p>
          <TransactionDetailCell
            entry={entry}
            locale={locale}
            connection={connection}
            element="div"
          />
          <dl className="dialog-facts">
            <dt>{copy.category}</dt>
            <dd>
              {entry.category_id
                ? categoryPath(categories, entry.category_id)
                : copy.uncategorized}
              {entry.category_rule && (
                <small> · {copy[`rule_${entry.category_rule}`]}</small>
              )}
            </dd>
            {entry.bank_category && (
              <>
                <dt>{copy.bankCategory}</dt>
                <dd>{entry.bank_category}</dd>
              </>
            )}
          </dl>
          {suggestion && !entry.category && (
            <div className="suggestion">
              <p>
                {copy.suggested} · {categoryPath(categories, suggestion)}
              </p>
              <div className="review-actions">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => onSave(suggestion, "merchant")}
                >
                  {copy.applySuggestion}
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={onDismissSuggestion}
                >
                  {copy.dismissSuggestion}
                </button>
              </div>
            </div>
          )}
          {editable ? (
            <form className="dialog-form" onSubmit={submit}>
              <label>
                {copy.category}
                <select
                  name="category"
                  defaultValue={entry.category_id ?? ""}
                  disabled={saving}
                >
                  <option value="">{copy.automaticCategory}</option>
                  {tree.map((top) => (
                    <optgroup key={top.id} label={top.name}>
                      <option value={top.id}>
                        {top.name} · {copy.wholeCategory}
                      </option>
                      {top.children.map((child) => (
                        <option key={child.id} value={child.id}>
                          {child.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <fieldset>
                <legend>{copy.ruleScope}</legend>
                {scopes
                  .filter((option) => option.available)
                  .map((option) => (
                    <label className="checkbox" key={option.value}>
                      <input
                        type="radio"
                        name="scope"
                        value={option.value}
                        checked={scope === option.value}
                        onChange={() => setScope(option.value)}
                        disabled={saving}
                      />
                      {option.label}
                    </label>
                  ))}
              </fieldset>
              <div className="review-actions">
                <button type="submit" disabled={saving}>
                  {copy.saveCategory}
                </button>
              </div>
            </form>
          ) : (
            <p>
              <small>{copy.categoryNotEditable}</small>
            </p>
          )}
        </>
      )}
    </Dialog>
  );
}
