"""Derive spending evidence without copying transaction descriptions into Silver."""

import hashlib
import re
import unicodedata
from decimal import Decimal

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
BANK_EXPENSE_OPERATIONS = {
    "CARTAO",
    "PACOTE_TARIFA_SERVICOS",
    "TARIFA_SERVICOS_AVULSOS",
}
NON_SPENDING = {
    "TRANSFER",
    "TRANSFERENCIA_MESMA_INSTITUICAO",
    "SAQUE",
    "PAGAMENTO",
    "PAGAMENTO_FATURA",
    "OPERACOES_CREDITO_CONTRATADAS_CARTAO",
    "CASHBACK",
}
REFUNDS = {"ESTORNO", "REFUND"}
# Pluggy category names; a debit moves money in, a credit takes it out.
INVESTMENT_CATEGORIES = {
    "investments",
    "automatic investment",
    "fixed income",
    "mutual funds",
    "variable income",
    "pension",
}
INVESTMENT_INCOME = {"proceeds interests and dividends", "taxes on investments"}
# Savings boxes ("caixinhas") arrive only as account transactions.
SAVINGS_BOX = {"dinheiro reservado": "contribution", "dinheiro retirado": "withdrawal"}
# Fixed-income movements that providers file as same-person transfers.
FIXED_INCOME = r"(cdb|lca|lci|cra|cri|lf|tesouro|debentures?)\b"
FIXED_INCOME_MOVES = {
    re.compile(rf"^(compra|aplicacao|aplicação) {FIXED_INCOME}"): "contribution",
    re.compile(rf"^(venda|vencimento|resgate) {FIXED_INCOME}"): "withdrawal",
    re.compile(rf"^(cupom|irrf) {FIXED_INCOME}"): "income",
}


def investment_kind(record: dict) -> str:
    category = normalize(record.get("category"))
    description = normalize(record.get("descriptionRaw") or record.get("description"))
    debit = record.get("type") == "DEBIT"
    for prefix, kind in SAVINGS_BOX.items():
        if description.startswith(prefix):
            return kind
    for pattern, kind in FIXED_INCOME_MOVES.items():
        if pattern.match(description):
            return kind
    if category in INVESTMENT_INCOME:
        return "income"
    if category in INVESTMENT_CATEGORIES:
        return "contribution" if debit else "withdrawal"
    return ""


def digits(value: object) -> str:
    return re.sub(r"\D", "", value) if isinstance(value, str) else ""


def printable(value: object, limit: int = 120) -> str:
    return value.strip()[:limit] if isinstance(value, str) and value.isprintable() else ""


def merchant_fields(record: dict) -> dict:
    """Business identity reported for the merchant or the other side of a transfer."""
    merchant = record.get("merchant")
    merchant = merchant if isinstance(merchant, dict) else {}
    card = record.get("creditCardMetadata")
    mcc = card.get("payeeMCC") if isinstance(card, dict) else None
    payment = record.get("paymentData")
    payment = payment if isinstance(payment, dict) else {}
    # The other side: who received a debit or who sent a credit.
    side = payment.get("receiver" if record.get("type") == "DEBIT" else "payer")
    side = side if isinstance(side, dict) else {}
    document = side.get("documentNumber")
    document = document if isinstance(document, dict) else {}
    kind = document.get("type") if document.get("type") in ("CPF", "CNPJ") else ""
    company = kind == "CNPJ" and len(digits(document.get("value"))) == 14
    category_id = record.get("categoryId")
    return {
        "category_id": category_id
        if isinstance(category_id, str) and category_id.isdigit()
        else "",
        "mcc": mcc if type(mcc) is int and 0 < mcc < 10000 else None,
        "merchant_cnpj": digits(merchant.get("cnpj"))
        if len(digits(merchant.get("cnpj"))) == 14
        else "",
        "merchant_cnae": digits(merchant.get("cnae"))[:7],
        "merchant_business_name": printable(merchant.get("businessName")),
        "merchant_category": printable(merchant.get("category"), 80),
        "counterparty_type": kind,
        # Personal documents and names stay in Bronze; only companies are identified.
        "counterparty_cnpj": digits(document.get("value")) if company else "",
        "counterparty_name": printable(side.get("name")) if company else "",
    }


def normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(re.findall(r"[^\W\d_]+", unicodedata.normalize("NFKC", value[:256]).casefold()))


def spending_fields(
    record: dict,
    transaction_key: str,
    *,
    card_account: bool = False,
    owners: frozenset[str] = frozenset(),
) -> dict:
    operation = record.get("operationType")
    operation = operation.upper().strip() if isinstance(operation, str) else ""
    payment_data = record.get("paymentData")
    payment_method = payment_data.get("paymentMethod") if isinstance(payment_data, dict) else None
    if not operation and isinstance(payment_method, str) and payment_method in PAYMENT_RAILS:
        operation = payment_method
    direction = record.get("type")
    provider_category = normalize(record.get("category"))
    hint = PROVIDER_CATEGORIES.get(provider_category, "")
    merchant = record.get("merchant")
    name = merchant.get("name") if isinstance(merchant, dict) else None
    business = merchant_fields(record)
    # A company on the other side of a transfer names the merchant when the provider does not.
    merchant_name = name.strip() if isinstance(name, str) else business["counterparty_name"]
    payment = record.get("paymentData")
    side = (
        payment.get("receiver" if direction == "DEBIT" else "payer")
        if isinstance(payment, dict)
        else None
    )
    document = side.get("documentNumber") if isinstance(side, dict) else None
    own_transfer = bool(owners) and (
        digits(document.get("value")) in owners if isinstance(document, dict) else False
    )
    label = merchant_name[:80] if merchant_name.isprintable() else ""
    merchant_match = normalize(merchant_name)
    match = merchant_match or normalize(record.get("description"))
    hint = hint or next(
        (MERCHANT_WORDS[word] for word in merchant_match.split() if word in MERCHANT_WORDS),
        "",
    )
    amount = record.get("amount")
    # Some connectors label positive card purchases PAGAMENTO.
    mislabeled_card_purchase = (
        operation == "PAGAMENTO"
        and card_account
        and direction == "DEBIT"
        and isinstance(record.get("creditCardMetadata"), dict)
        and isinstance(amount, (int, float, Decimal))
        and not isinstance(amount, bool)
        and amount > 0
    )
    investment = "" if card_account else investment_kind(record)
    excluded = (
        bool(investment)
        or own_transfer
        or (operation in NON_SPENDING and not mislabeled_card_purchase)
        or any(
            word in provider_category
            for word in ("transfer", "bill payment", "credit card payment")
        )
    )
    kind = ""
    if not excluded:
        if direction == "CREDIT" and operation in REFUNDS:
            kind = "refund"
        elif direction == "DEBIT" and operation not in REFUNDS:
            has_evidence = operation not in PAYMENT_RAILS and (
                hint
                or operation in BANK_EXPENSE_OPERATIONS
                or card_account
                or isinstance(record.get("creditCardMetadata"), dict)
            )
            kind = "purchase" if has_evidence else "review"
    return business | {
        "own_transfer": own_transfer,
        "investment_kind": investment,
        "spending_kind": kind,
        "spending_category": hint,
        "spending_operation": operation if kind and operation in PAYMENT_RAILS else "",
        "merchant_label": label if kind else "",
        "merchant_key": (
            hashlib.sha256(
                ("merchant:" + match if match else "transaction:" + transaction_key).encode()
            ).hexdigest()
            if kind
            else ""
        ),
    }
