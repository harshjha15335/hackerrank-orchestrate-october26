# Usage report: final full-dataset run

The run that produced `output.csv` was `python3 code/main.py`, on 518 requests from `dataset/deletion_requests.csv`.

The output SHA-256 is `252b026188daea2fe4b72a5bcbaaefe4dbd98c991bc40b53ecbedd4727352e3c`, and the file is reproduced byte-for-byte by a second run.

## Model usage

| Provider | Model | Model calls | Input tokens | Output tokens | Total tokens | Avg tokens / request | Est. cost (total) | Est. cost / request |
|---|---|---|---|---|---|---|---|---|
| none | none | 0 | 0 | 0 | 0 | 0 | $0.00 | $0.00 |
| **Overall** | | **0** | **0** | **0** | **0** | **0** | **$0.00** | **$0.00** |

The final run makes no model or network calls. Every stage is deterministic code:

- **Intent (M3):** offline rules in `code/intent/classifier.py`. No provider is configured, so no request is routed to a model (`intent_requests_routed_to_unconfigured_model: 0`).
- **Screenshots (M8):**
  - Facts come from committed, manually transcribed fixtures under `code/vision/`. The extraction prompt in `code/vision/prompt.md` documents the schema those fixtures follow.
  - The runtime ledger records 0 vision model calls and 0 tokens.
- **Ingest, identity, state, policy, flows, synthesis and citation guard:** standard-library Python, plus `pdftotext` (poppler-utils) for PDF text and `sqlite3` for SQL snapshots.

These values come from the run ledger in `code/evaluation/checkpoints/FINAL_METRICS.json` (`usage`): `runtime_model_calls: 0`, `input_tokens: 0`, `output_tokens: 0`, `cost_usd: 0.0`.

AI coding assistants were used to build the solution; their sessions are recorded in `log.txt`. That development-time assistance is not part of the solution's runtime and is not counted above.
