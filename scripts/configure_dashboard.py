"""Provision the local dashboard service account in the owned private directory."""

import hashlib
import os
import re
import secrets
import tempfile
from pathlib import Path

from scripts.phase0 import validate_private_path


def configure(private: Path) -> None:
    private = validate_private_path(private)
    marker = private / ".finance-phase0"
    directory = private / "secrets"
    password_file = directory / "dashboard_password"
    config_file = directory / "dashboard.xml"
    if any(
        path.is_symlink() or path.is_junction()
        for path in (directory, marker, password_file, config_file)
    ):
        raise ValueError("Linked dashboard credential paths are forbidden")
    if marker.read_text(encoding="utf-8").strip() != "synthetic-only-v1":
        raise ValueError("Private directory ownership could not be verified")
    if not password_file.exists():
        with password_file.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_hex(32))
    password = password_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        raise ValueError("Invalid dashboard credential file")
    digest = hashlib.sha256(password.encode()).hexdigest()
    config = (
        "<clickhouse><users><dashboard>"
        f"<password_sha256_hex>{digest}</password_sha256_hex>"
        "<networks><ip>0.0.0.0/0</ip></networks><profile>default</profile>"
        "<quota>default</quota><grants>"
        "<query>GRANT SELECT ON analytics.spending_current</query>"
        "<query>GRANT SELECT ON analytics.spending_dashboard</query>"
        "<query>GRANT SELECT ON analytics.accounts_dashboard</query>"
        "<query>GRANT SELECT ON analytics.account_balance_history</query>"
        "<query>GRANT SELECT ON analytics.pending_card_spending</query>"
        "<query>GRANT SELECT ON analytics.investment_flows</query>"
        "<query>GRANT SELECT ON analytics.invested_balances</query>"
        "<query>GRANT SELECT ON analytics.savings_boxes</query>"
        "<query>GRANT SELECT ON analytics.savings_box_history</query>"
        "<query>GRANT SELECT ON analytics.savings_box_outflows</query>"
        "<query>GRANT SELECT ON analytics.own_transfers</query>"
        "<query>GRANT SELECT ON analytics.investments_dashboard</query>"
        "<query>GRANT SELECT ON analytics.spending_categories</query>"
        "<query>GRANT INSERT ON core.spending_categories</query>"
        "<query>GRANT INSERT ON core.category_rules</query>"
        "<query>GRANT SELECT ON analytics.manual_expenses</query>"
        "<query>GRANT SELECT ON analytics.provider_spending</query>"
        "<query>GRANT INSERT ON core.manual_expenses</query>"
        "<query>GRANT SELECT ON analytics.inferred_payment_dismissals</query>"
        "<query>GRANT INSERT ON core.inferred_payment_dismissals</query>"
        "<query>GRANT SELECT ON analytics.investment_classes</query>"
        "<query>GRANT SELECT ON analytics.investment_class_assignments</query>"
        "<query>GRANT SELECT ON analytics.investment_position_history</query>"
        "<query>GRANT SELECT ON analytics.investment_position_movements</query>"
        "<query>GRANT SELECT ON analytics.market_rates</query>"
        "<query>GRANT INSERT ON core.investment_classes</query>"
        "<query>GRANT INSERT ON core.investment_class_assignments</query>"
        "<query>GRANT SYSTEM RELOAD DICTIONARY ON *.*</query>"
        "<query>GRANT INSERT ON core.spending_reviews</query>"
        "</grants></dashboard></users></clickhouse>"
    )
    if not config_file.exists() or config_file.read_text(encoding="utf-8") != config:
        with tempfile.TemporaryDirectory(dir=directory) as staging:
            temporary = Path(staging) / config_file.name
            temporary.write_text(config, encoding="utf-8")
            temporary.replace(config_file)
    if os.name != "nt":
        for path in (password_file, config_file):
            path.chmod(0o444)


if __name__ == "__main__":
    try:
        configure(Path(os.environ["FINANCE_PRIVATE_DIR"]))
    except (OSError, ValueError, KeyError):
        raise SystemExit("Dashboard credential setup failed.") from None
