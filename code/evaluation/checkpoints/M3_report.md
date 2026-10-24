# M3 — deletion-intent classification — PASS for independent review

Date: 2026-10-24. Branch: `feature/m3-deletion-intent`, based on merged M2
`main` commit `1a74d06f76713abeba4c614203fea358c6ebff3b`.

## Implementation

`code/intent/classifier.py` has ordered, rules-first intent classification,
safe optional model routing, strict JSON reply validation and cache keys from
model ID, prompt version and canonical request text. It returns intent,
route, reason, degradation and model-call count. `code/intent/main.py` is the
reproducible offline CLI; it reads only `request_text`, writes JSON to stdout,
and can create an exact-text private route log outside the checkout.
`code/intent/tests/test_intent.py` contains synthetic adversarial cases,
participant sample checks, mock model/caching tests, strict-reply rejection,
spotlighting checks, offline socket blocking and CLI repeatability. No
production code reads `sample_output.csv`, and `code/main.py` is unchanged.

## Acceptance evidence

| Gate | Result |
|---|---|
| M3-1 | 32/32 public sample request texts classified `DELETE`; development 22/22 and holdout 10/10. Sample gold was not consulted. |
| M3-2 | 30/30 independently written adversarial fixtures passed, including negation, access, export, corrections, marketing-only opt-out, six language forms, historical mentions, hypotheticals, quotes, third-party instructions and multilingual injection. |
| M3-3 | All 518 evaluation texts classified: `DELETE` 508, `NOT_APPLICABLE` 10, `UNCERTAIN` 0. Routed to model/offline fallback: 0; the exact routed-text list is empty. No manual correctness review or evaluation labels are claimed. |
| M3-4 | Mocked ambiguous request: first call 1, warm-cache call 0. Cache identity changes when model ID or request changes; normalized equivalent requests share a key. Full offline runs each made 0 calls. |
| M3-5 | Synthetic ambiguous and injected requests deterministically return `UNCERTAIN`, `degraded=true` without a provider. Full participant run: degraded 0. |

The exact routed texts for the full offline run were written to
`/tmp/m3-routes.json` as `[]` and were not committed. The CLI's decisions
are reproducible with `python3 code/intent/main.py` and
`python3 code/intent/main.py --sample`. The full-run JSON SHA-256 was
`a0ec7690df539594054accc21153df0dc3bbedb0aa200c8a4e94fc15f09f506a`;
the sample-run SHA-256 was
`40c9d18210d0a256014ef537eed1cb43dffd21cf15c0de7bd95cecc7bf419175`.
No real model was configured or called; provider, token usage and cost are
therefore inapplicable, not estimated.

The complete M0–M3 suite, run with
`/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests code/identity/tests code/intent/tests`,
reported **158 passed in 10.17s**, zero failures or skips. `git diff --check`
also passed. M0–M2 had 117 passing tests in the prior milestone; this run
adds 41 M3 test cases.

## May source comparison

| Reference | Inspected path | Adaptation for October |
|---|---|---|
| Saai | `benchmarks/saai-winner/code/runner/pipeline.py:196-240` | Cheap pre-model rule cascade adapted to deletion authorization; support-ticket out-of-scope and pleasantry outcomes were not reused. |
| Saai | `benchmarks/saai-winner/code/agent/classifier.py` | Disk cache and minimal constrained reply adapted; key also includes explicit model ID and prompt version, and malformed replies are rejected instead of silently coerced. No Haiku or paid inference call was made. |
| Saai | `benchmarks/saai-winner/code/agent/middleware/prompt_injection.py` | Multilingual injection markers route to uncertainty; a support-ticket refusal cannot safely establish deletion intent. |
| LeeRenJie | `benchmarks/leerenjie/code/drafter.py:94-97` | Delimited untrusted request text and escaped closing tag; document drafting/citation pipeline was not imported into intent classification. |
| Amogh | `benchmarks/amogh/code/test_classifier.py` | Deterministic independent edge-case tests adapted to privacy intent, with socket blocking and mock model calls. Support-ticket company or product-area labels are irrelevant here. |

## Limits and recommendation

**PASS for M3 independent review.** The 518 distribution is an intent output,
not verified accuracy: those requests have no provided intent labels.
Rule coverage is finite, especially for paraphrases and language variants;
unrecognized cases become explicitly uncertain offline. A live model provider
and provider-specific call ledger are not configured or tested. The model
cache test uses a deterministic mock. Intent classification does not assess
evidence state or decide COMPLETE versus INCOMPLETE. M4 remains unstarted.
