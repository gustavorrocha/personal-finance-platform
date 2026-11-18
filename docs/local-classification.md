# Local category suggestions

The dashboard can ask Ollama to suggest a category for an expense after
deterministic classification. The model receives only cleaned structured
merchant labels. It receives no financial amounts, identifiers, or raw
transaction descriptions. A merchant label can still contain personal text.
Inference runs inside Docker on the private AI network with cloud features disabled.

## Set up and try

Use Docker Desktop's Linux engine. The model download is about 1.4 GB and the
runtime container has a 3 GB memory limit.
[Ollama Qwen3 model library](https://ollama.com/library/qwen3:1.7b)

```powershell
.\scripts\install_local_model.ps1
.\scripts\run_local.ps1
uv run --frozen finance demo-spending
```

The install step has registry access only in a temporary downloader container.
It mounts only the private model directory. The regular runtime has no published
Ollama port and uses the existing internal AI network.

Choose **Synthetic demo**, then **Suggest categories** under **Recent expenses**.
Each request checks up to four uncategorized expenses with merchant labels.
**Apply as merchant rule** saves the selected category through the regular
dashboard rule flow. **Dismiss** clears the proposal for the current session.
Totals, debit reviews, and other categories stay under the existing rules.

## Validation and caching

Ollama receives a JSON schema with the supported categories and a required
review flag. The API validates the full response and returns only its category.
Unknown categories, malformed output, and incomplete responses are discarded.
The cache holds up to 128 proposals or abstentions in memory. Its keys include
the model digest, instructions, taxonomy, and cleaned label. Suggestions are
transient. Applied merchant rules persist as regular spending rule events.
[Ollama generate API](https://docs.ollama.com/api/generate)

Run the labeled synthetic benchmark from the API container after setup.

```powershell
docker compose --env-file .env -f infra/compose.yaml exec -T api /app/.venv/bin/python -m finance_api.benchmark_model
```

The benchmark reports matches, abstentions, macro-F1, and elapsed time for
initial and repeated classification. Eight invented labels provide a smoke
check. Accuracy on representative private data, comparisons with other
classifiers, and separate long-term suggestion history remain outside this slice.

On Docker Desktop, Qwen3 matched 5 of 8 synthetic labels with a macro-F1 of 0.50.
The first pass took 21.2 seconds, the cached pass 0.33 seconds, and Ollama used
about 1.58 GiB during the test. These cases also guided prompt tuning. Chrome
verified Portuguese suggestions, explicit approval, and dismissal. A probe
from the Ollama runtime network namespace could not reach an external TCP
endpoint. The full Python suite passed 88 tests and the frontend suite passed 6.
