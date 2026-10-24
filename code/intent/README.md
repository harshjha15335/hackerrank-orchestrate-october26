# M3 deletion intent

Run `python3 code/intent/main.py --sample` for the 32 participant sample
requests, or `python3 code/intent/main.py` for all 518 evaluation requests.
Both commands emit deterministic JSON to stdout and read request text only.
Neither reads sample answers, audits resources, or creates `output.csv`.

The classifier returns `DELETE`, `NOT_APPLICABLE`, or `UNCERTAIN`, with a route,
reason, and degradation flag. High-confidence rules handle explicit deletion,
negation, common non-deletion requests, multilingual statements and deletion
audit followups. Ambiguous, quoted, hypothetical, third-party and suspicious
instructions go to an optional injected `model_call(system, user)` callback.
The CLI has no provider configured, so such requests return `UNCERTAIN` with
`degraded=true`. A future caller may supply a provider and explicit model ID;
model replies must be a strict JSON boolean. The cache key hashes the model
ID, prompt version and normalized request text. Cached calls are validated
again and cost zero model calls. Request text is delimited and a closing-tag
sequence is escaped before the model receives it.

For local review of ambiguous routing, pass `--route-log /tmp/m3-routes.json`.
The path must be new and outside the repository. It contains exact routed
request texts and should not be committed. A model integration should retain
equivalent private routing diagnostics, including its final decision.

Run tests with
`python3 -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests code/identity/tests code/intent/tests`.
