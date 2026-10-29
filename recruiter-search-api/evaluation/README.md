# Search evaluation

`benchmark.json` is the maintainable query set. It intentionally starts with
empty candidate and requirement judgments; do not interpret result counts or
CrossEncoder scores as accuracy. Add judgments only after a recruiter reviews
the candidates. Set `complete: true` only when relevance has been judged for
the full candidate corpus for that query.

Run the live benchmark against the local API:

```powershell
python -m evaluation.run_benchmark --url http://127.0.0.1:8000
```

Runs are stored under `evaluation/runs/`. Compare a later run with an earlier
JSON artifact:

```powershell
python -m evaluation.run_benchmark --compare evaluation/runs/run-YYYYMMDD-HHMMSS.json
```

The API request enables bounded debug tracing for the benchmark only. It
records IDs and at most three short evidence chunks per candidate in its
retrieval, chunk reranking, consolidation, candidate validation, and
qualification stages. Normal UI search requests do not enable this trace.
Stage-wise precision/recall is reported only when judgments support it;
otherwise the report shows `UNAVAILABLE`, while result-set and ranking changes
remain available for inspection.

Candidate relevance judgments can be represented as either:

```json
"candidates": [
  {"candidate_id": 123, "relevant": true},
  {"candidate_id": 456, "relevant": false}
]
```

or a candidate ID to boolean map. Requirement-level judgments use
`requirements: [{"requirement": "...", "candidates": [...], "complete": false}]`.
Unjudged candidates do not count as irrelevant. Consequently, precision@k is
available only when every returned top-k candidate is judged, and recall only
when the judgment set is marked complete.

## Latency and relevance configuration

The current pipeline bounds CrossEncoder work with `MAX_CHUNK_RERANK_PAIRS`
(default 160), `MAX_CANDIDATE_VALIDATION_PAIRS` (default 64),
`MAX_EVIDENCE_PER_CANDIDATE` (default 3), and `RERANK_BATCH_SIZE` (default 64).
Candidate validation compares the model's raw relevance score with
`CANDIDATE_VALIDATION_MIN_SCORE` (default 0.0). That score is neither a
probability nor an accuracy measure, and the default threshold is provisional:
calibrate it against reviewed requirement-level judgments before treating it
as a production-quality decision boundary.

The benchmark measures actual API latency. It does not claim latency gains or
search accuracy from a single run; compare repeated runs under similar server
and model conditions.
