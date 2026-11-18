"""Run a small labeled synthetic benchmark from the internal API container."""

import asyncio
import json
from time import monotonic

import httpx

from .local_classifier import BATCH_LIMIT, MODEL_TIMEOUT, LocalClassifier

CASES = {
    "Corner Bookshop": "Shopping",
    "Metro Ticket Office": "Transport",
    "Neighborhood Supermarket": "Groceries",
    "Café da Praça": "Dining",
    "Clínica Bom Jardim": "Health",
    "City Cinema": "Leisure",
    "Residential Electric Utility": "Home",
    "Farmácia do Bairro": "Health",
}


async def benchmark() -> None:
    classifier = LocalClassifier()
    labels = list(CASES)
    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT, trust_env=False) as client:

        async def classify():
            predictions = []
            for start in range(0, len(labels), BATCH_LIMIT):
                predictions.extend(
                    await classifier.suggest(client, labels[start : start + BATCH_LIMIT])
                )
            return predictions

        began = monotonic()
        predictions = await classify()
        first_seconds = monotonic() - began
        began = monotonic()
        await classify()
        cached_seconds = monotonic() - began
    pairs = list(zip(CASES.values(), predictions, strict=True))
    matches = sum(expected == predicted for expected, predicted in pairs)
    counts = []
    for category in set(CASES.values()):
        correct = sum(expected == predicted == category for expected, predicted in pairs)
        actual = sum(expected == category for expected, _ in pairs)
        predicted_count = sum(predicted == category for _, predicted in pairs)
        counts.append(2 * correct / (actual + predicted_count))
    print(
        json.dumps(
            {
                "synthetic_cases": len(CASES),
                "matched": matches,
                "abstentions": predictions.count(None),
                "macro_f1": round(sum(counts) / len(counts), 3),
                "first_seconds": round(first_seconds, 2),
                "repeat_seconds": round(cached_seconds, 2),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(benchmark())
    except Exception:
        raise SystemExit("Synthetic classification benchmark could not run locally.") from None
