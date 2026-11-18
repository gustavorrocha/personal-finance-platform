"""Derive spending evidence without copying transaction descriptions into Silver."""

import hashlib
import re
import unicodedata

PROVIDER_CATEGORIES = {
    "groceries": "Groceries",
    "food and drinks": "Dining",
    "restaurants": "Dining",
    "transport": "Transport",
    "transportation": "Transport",
    "home": "Home",
    "shopping": "Shopping",
    "health": "Health",
    "entertainment": "Leisure",
}
MERCHANT_WORDS = {
    "supermarket": "Groceries",
    "supermercado": "Groceries",
    "cafe": "Dining",
    "café": "Dining",
    "restaurante": "Dining",
    "pharmacy": "Health",
    "farmácia": "Health",
}
PAYMENT_RAILS = {"PIX", "TED", "DOC"}
NON_SPENDING = {
    "TRANSFER",
    "PAGAMENTO",
    "PAGAMENTO_FATURA",
    "OPERACOES_CREDITO_CONTRATADAS_CARTAO",
    "CASHBACK",
}
REFUNDS = {"ESTORNO", "REFUND"}


def normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(re.findall(r"[^\W\d_]+", unicodedata.normalize("NFKC", value[:256]).casefold()))


def spending_fields(record: dict, transaction_key: str, *, card_account: bool = False) -> dict:
    operation = record.get("operationType")
    operation = operation.upper().strip() if isinstance(operation, str) else ""
    direction = record.get("type")
    provider_category = normalize(record.get("category"))
    hint = PROVIDER_CATEGORIES.get(provider_category, "")
    merchant = record.get("merchant")
    name = merchant.get("name") if isinstance(merchant, dict) else None
    merchant_name = name.strip() if isinstance(name, str) else ""
    label = merchant_name[:80] if merchant_name.isprintable() else ""
    merchant_match = normalize(merchant_name)
    match = merchant_match or normalize(record.get("description"))
    hint = hint or next(
        (MERCHANT_WORDS[word] for word in merchant_match.split() if word in MERCHANT_WORDS),
        "",
    )
    excluded = operation in NON_SPENDING or any(
        word in provider_category for word in ("transfer", "bill payment", "credit card payment")
    )
    kind = ""
    if not excluded:
        if direction == "CREDIT" and operation in REFUNDS:
            kind = "refund"
        elif direction == "DEBIT" and operation not in REFUNDS:
            has_evidence = operation not in PAYMENT_RAILS and (
                hint or card_account or isinstance(record.get("creditCardMetadata"), dict)
            )
            kind = "purchase" if has_evidence else "review"
    return {
        "spending_kind": kind,
        "spending_category": hint,
        "merchant_label": label if kind else "",
        "merchant_key": (
            hashlib.sha256(
                ("merchant:" + match if match else "transaction:" + transaction_key).encode()
            ).hexdigest()
            if kind
            else ""
        ),
    }
