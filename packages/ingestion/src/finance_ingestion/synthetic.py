"""Fixed, wholly invented capture used by local and CI acceptance checks."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from finance_lake.bronze import BronzeLake
from finance_lake.manifest import Manifest

SYNTHETIC_RUN = UUID("11111111-1111-4111-8111-111111111111")


def capture_synthetic(lake: BronzeLake, fixtures: Path) -> Manifest:
    payloads = [
        (resource, (fixtures / f"{resource}-response.json").read_bytes())
        for resource in ("accounts", "transactions")
    ]
    return lake.commit(
        run_id=SYNTHETIC_RUN,
        retrieved_at=datetime(2026, 11, 17, 12, tzinfo=UTC),
        item_alias="synthetic-demo",
        payloads=payloads,
    )
