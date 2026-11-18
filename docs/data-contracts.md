# Bronze and synthetic replay contracts

This document describes the v1 synthetic contracts. Provider capture and typed Silver
contracts are described in the [provider ingestion runbook](provider-ingestion.md).

## Files and identity

The Lake lives under `FINANCE_PRIVATE_DIR/lake`, outside Git and cloud sync.
An ownership marker identifies a store initialized by `LocalObjectStore`.

```text
bronze/source=synthetic/resource=<resource>/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.json.gz
manifests/ingestion_date=YYYY-MM-DD/run_id=<uuid>/manifest.json
quarantine/run_id=<uuid>/status.json
quarantine/run_id=<uuid>/<observed-sha256>.bin
quarantine/run_id=<uuid>/event-<event-sha256>.json
```

Keys never include account/customer identifiers or aliases. Allowed resources are
accounts, transactions, investments, investment_movements and bills. Endpoint
metadata contains only the corresponding fixed path, with no query strings.

One run ID identifies one capture/observation, not an indefinitely reusable sync
job. Retrying the same capture uses the same UUID, UTC retrieval time, alias and
response bytes. Different metadata/bytes under that identity fail closed. A new
observation deliberately uses a new UUID even when its response contents match.

Objects preserve the entire original JSON response bytes under gzip, including
envelope fields. They do not serialize decoded records back into the original.
Gzip headers omit filename/time; existing identical raw objects are reused if
runtime compression output changes. Temp/orphan files do not constitute a commit.

## Manifest v1

`Manifest` and `BronzeObject` are closed Pydantic contracts; unknown fields fail.
The manifest is canonical UTF-8 JSON and contains:

- Run UUID, synthetic source/alias/consent, UTC retrieval timestamp, collector and
  manifest versions, status and reference interval. The synthetic reference interval
  is the retrieval date; historical financial periods are not inferred.
- For each part: resource, safe endpoint, ordinal, object UUID/key, compressed and
  raw SHA-256, compressed/raw sizes, record count, schema fingerprint and optional
  previous object UUIDs. Fixtures have no previous objects.

Object UUIDs derive deterministically from run/resource/part/raw hash. Record UUIDs
derive from object UUID and zero-based response position; neither ticker, amount
nor account/date heuristics establish financial identity. Duplicate JSON keys,
non-finite numbers and a missing/non-object `results` array are rejected.

Limits: 8 MiB expanded JSON per object, 16 MiB stored object, 32 MiB expanded capture,
128 parts, 10,000 records per part. Inputs exceeding limits are refused. Checksums
cover bytes; schema fingerprints cover shapes rather than values.

## Quarantine and recovery

Verification checks the whole capture before yielding any records. Missing files,
hash/size/schema/count mismatches and malformed manifests fail closed. Available
corrupt bytes are copied into private quarantine; evidence is not logged or
silently overwritten. A sticky status marker prevents automatic resurrection.
Manual repair/reset and deletion are not commands in this phase.

After a crash before the manifest, retry the identical capture; complete objects
are reused, incomplete temporary files are ignored. After a crash after the
manifest or during metadata registration, replay from the manifest. No provider
or external network is required. Lake listing does not imply freshly verified
integrity; `lake verify` does the full check.

## ClickHouse grains and read rules

| Table/view | Grain and semantics |
|---|---|
| `metadata.bronze_objects` | Run UUID × object UUID; append/replacing events, complete=1 and quarantined=2 |
| `metadata.bronze_objects_current` | Exact current row per run/object using `FINAL`, including quarantine status |
| `metadata.synthetic_bronze_record_versions` | Build UUID × run UUID × object UUID × record UUID; original decoded record JSON for synthetic replay evidence |
| `metadata.synthetic_bronze_publications` | One publication event per successful build, monotonically increasing version under single-writer operation |
| `metadata.synthetic_bronze_records_published` | Exact records from the latest complete publication, resolved before aggregation |

Repeated writes can coexist physically until merges; never aggregate the base
tables as current state. Index timestamps are technical observations, not financial
dates. A warehouse rebuild derives indexes/records from committed files; it does
not fetch data or touch future financial core/analytics models.

Migration 0002 also contains the initial synthetic replay table/current view.
Migration 0003 preserves those rows under a compatibility build and introduces
generation publication without rewriting an applied migration. New consumers use
the `published` view above. Old experimental staging tables are not a data source.

Automatic storage erasure depends on a retention policy covering live references,
quarantine evidence, prior generations and backups.
