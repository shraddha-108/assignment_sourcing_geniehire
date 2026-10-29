"""Run and compare query-wise GenieHire search evaluation snapshots.

Candidate accuracy metrics are emitted only when human judgments support
them. With the starter benchmark, judgments are intentionally empty.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = ROOT / "benchmark.json"
RUNS_DIR = ROOT / "runs"


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _request_search(base_url: str, query: str, timeout: float) -> dict:
    payload = json.dumps({"query": query, "debug": True}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _candidate_ids(response: dict) -> list[str]:
    return [str(item.get("candidate_id", item.get("id")))
            for item in response.get("results", [])
            if item.get("candidate_id", item.get("id")) is not None]


def _ranking_delta(before: list, after: list) -> dict:
    before_ids = [str(value) for value in before]
    after_ids = [str(value) for value in after]
    common = set(before_ids).intersection(after_ids)
    before_order = [value for value in before_ids if value in common]
    after_order = [value for value in after_ids if value in common]
    return {
        "added": [value for value in after_ids if value not in before_ids],
        "removed": [value for value in before_ids if value not in after_ids],
        "common_candidate_order_changed": before_order != after_order,
    }


def _run_one(base_url: str, entry: dict, timeout: float) -> dict:
    started = time.perf_counter()
    try:
        response = _request_search(base_url, entry["query"], timeout)
        elapsed = time.perf_counter() - started
        result_ids = _candidate_ids(response)
        execution_trace = response.get("execution_trace", {})
        shadow_baseline_ids = execution_trace.get("semantic_debug", {}).get("legacy_result_ids")
        return {
            "query_id": entry["id"],
            "query": entry["query"],
            "category": entry["category"],
            "route": response.get("route"),
            "valid": response.get("valid", True),
            "result_ids": result_ids,
            "result_count": len(response.get("results", [])),
            "latency_seconds": round(elapsed, 4),
            "parsed": response.get("parsed"),
            "execution_trace": execution_trace,
            "shadow_comparison": ({
                "baseline_result_ids": shadow_baseline_ids,
                "current_result_ids": result_ids,
                **_ranking_delta(shadow_baseline_ids, result_ids),
                "accuracy_status": "UNAVAILABLE",
                "accuracy_reason": "No human-reviewed candidate judgments.",
            } if shadow_baseline_ids is not None else None),
            "stage_evaluation": _stage_metrics(
                {"execution_trace": response.get("execution_trace", {}),
                 "result_ids": _candidate_ids(response)},
                entry.get("ground_truth", {}), entry.get("top_k", 10),
            ),
            "requirement_evaluation": _requirement_evaluation(
                {"execution_trace": response.get("execution_trace", {})},
                entry.get("ground_truth", {}).get("requirements", []),
                entry.get("top_k", 10),
            ),
            "error": None,
        }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "query_id": entry["id"],
            "query": entry["query"],
            "category": entry["category"],
            "valid": False,
            "result_ids": [],
            "result_count": 0,
            "latency_seconds": round(time.perf_counter() - started, 4),
            "execution_trace": {},
            "error": str(exc),
        }


def _judgment_map(ground_truth: dict) -> dict[str, bool]:
    judgments = ground_truth.get("candidates", [])
    if isinstance(judgments, dict):
        return {str(candidate_id): bool(relevant)
                for candidate_id, relevant in judgments.items()}
    return {
        str(item["candidate_id"]): bool(item["relevant"])
        for item in judgments
        if item.get("candidate_id") is not None and "relevant" in item
    }


def _metrics(result_ids: list[str], ground_truth: dict, top_k: int) -> dict:
    judgments = _judgment_map(ground_truth)
    if not judgments:
        return {"precision_at_k": None, "recall": None,
                "false_positives": None, "false_negatives": None,
                "status": "UNAVAILABLE", "reason": "No candidate relevance judgments."}

    top_ids = result_ids[:top_k]
    all_top_k_judged = all(candidate_id in judgments for candidate_id in top_ids)
    precision = None
    false_positives = None
    if all_top_k_judged:
        true_positives = sum(judgments[candidate_id] for candidate_id in top_ids)
        precision = true_positives / len(top_ids) if top_ids else 0.0
        false_positives = len(top_ids) - true_positives

    complete = bool(ground_truth.get("complete", False))
    recall = false_negatives = None
    if complete:
        relevant_ids = {candidate_id for candidate_id, relevant in judgments.items() if relevant}
        if relevant_ids:
            returned_relevant = len(relevant_ids.intersection(result_ids))
            recall = returned_relevant / len(relevant_ids)
            false_negatives = len(relevant_ids) - returned_relevant
        else:
            recall = 1.0 if not result_ids else 0.0
            false_negatives = 0

    metric_status = "AVAILABLE" if precision is not None or recall is not None else "PARTIAL"
    reason = None
    if precision is None:
        reason = "Top-k precision unavailable: at least one returned candidate lacks a judgment."
    elif recall is None:
        reason = "Recall unavailable: candidate judgments are not marked complete for the corpus."
    return {"precision_at_k": precision, "recall": recall,
            "false_positives": false_positives, "false_negatives": false_negatives,
            "status": metric_status, "reason": reason}


def _stage_candidate_ids(item: dict, stage: str) -> list[str]:
    trace = item.get("execution_trace", {}).get("semantic_debug", {})
    if stage == "baseline":
        ids = trace.get("legacy_result_ids")
    elif stage == "chunk_reranking":
        ids = trace.get("chunk_reranking", {}).get("candidate_order")
    elif stage == "candidate_validation":
        ids = trace.get("candidate_validation_passed_ids")
    else:
        ids = trace.get("qualified_result_ids") or item.get("result_ids", [])
    return [str(value) for value in (ids or [])]


def _stage_metrics(item: dict, ground_truth: dict, top_k: int) -> dict:
    return {
        stage: {
            "result_ids": ids,
            "result_count": len(ids),
            **_metrics(ids, ground_truth, top_k),
        }
        for stage in ("baseline", "chunk_reranking", "candidate_validation", "final")
        for ids in [_stage_candidate_ids(item, stage)]
    }


def _requirement_predictions(item: dict, requirement_text: str,
                             baseline: bool = False) -> list[str]:
    trace = item.get("execution_trace", {}).get("semantic_debug", {})
    decision_key = "legacy_requirement_decisions" if baseline else "requirement_decisions"
    wanted = " ".join(requirement_text.casefold().split())
    predictions = []
    for candidate in trace.get("qualification", []):
        for decision in candidate.get(decision_key, []):
            actual = " ".join(str(decision.get("requirement") or "").casefold().split())
            if actual == wanted and decision.get("matched"):
                predictions.append(str(candidate.get("candidate_id")))
                break
    return predictions


def _requirement_evaluation(item: dict, judgments: list[dict], top_k: int) -> dict:
    output = {}
    for judgment in judgments:
        requirement = str(judgment.get("requirement") or "")
        ground_truth = {
            "candidates": judgment.get("candidates", []),
            "complete": bool(judgment.get("complete", False)),
        }
        baseline_ids = _requirement_predictions(item, requirement, baseline=True)
        current_ids = _requirement_predictions(item, requirement)
        output[requirement] = {
            "baseline": {"result_ids": baseline_ids,
                         **_metrics(baseline_ids, ground_truth, top_k)},
            "current": {"result_ids": current_ids,
                        **_metrics(current_ids, ground_truth, top_k)},
            "added": [value for value in current_ids if value not in baseline_ids],
            "removed": [value for value in baseline_ids if value not in current_ids],
        }
    return output


def _result_map(run: dict) -> dict[str, dict]:
    return {item["query_id"]: item for item in run.get("queries", [])}


def compare_runs(benchmark: dict, baseline: dict, current: dict,
                 regression_threshold: float) -> dict:
    baseline_queries = _result_map(baseline)
    current_queries = _result_map(current)
    comparisons = []
    deltas = []
    for entry in benchmark["queries"]:
        query_id = entry["id"]
        before = baseline_queries.get(query_id)
        after = current_queries.get(query_id)
        if before is None or after is None:
            comparisons.append({"query_id": query_id, "status": "MISSING_RUN",
                                "metrics": "UNAVAILABLE"})
            continue

        before_metrics = _metrics(before.get("result_ids", []),
                                  entry.get("ground_truth", {}), entry.get("top_k", 10))
        after_metrics = _metrics(after.get("result_ids", []),
                                 entry.get("ground_truth", {}), entry.get("top_k", 10))
        p_before, p_after = before_metrics["precision_at_k"], after_metrics["precision_at_k"]
        if p_before is not None and p_after is not None:
            delta = p_after - p_before
            deltas.append((p_before, p_after))
            status = "REGRESSION" if delta <= -regression_threshold else (
                "IMPROVED" if delta >= regression_threshold else "UNCHANGED"
            )
        else:
            status = "UNAVAILABLE"

        before_ids = before.get("result_ids", [])
        after_ids = after.get("result_ids", [])
        stage_comparison = {}
        for stage in ("baseline", "chunk_reranking", "candidate_validation", "final"):
            before_stage_ids = _stage_candidate_ids(before, stage)
            after_stage_ids = _stage_candidate_ids(after, stage)
            stage_comparison[stage] = {
                "baseline": {"result_ids": before_stage_ids,
                             **_metrics(before_stage_ids, entry.get("ground_truth", {}), entry.get("top_k", 10))},
                "current": {"result_ids": after_stage_ids,
                            **_metrics(after_stage_ids, entry.get("ground_truth", {}), entry.get("top_k", 10))},
                "added": [value for value in after_stage_ids if value not in before_stage_ids],
                **_ranking_delta(before_stage_ids, after_stage_ids),
            }
        comparisons.append({
            "query_id": query_id,
            "query": entry["query"],
            "category": entry["category"],
            "status": status,
            "route_changed": before.get("route") != after.get("route"),
            "interpretation_changed": before.get("parsed") != after.get("parsed"),
            "baseline": {"result_count": before.get("result_count"),
                         "result_ids": before_ids, **before_metrics},
            "current": {"result_count": after.get("result_count"),
                        "result_ids": after_ids, **after_metrics},
            **_ranking_delta(before_ids, after_ids),
            "latency_seconds": {"baseline": before.get("latency_seconds"),
                                "current": after.get("latency_seconds")},
            "stages": stage_comparison,
        })

    summary = {"total_queries": len(comparisons), "improved": 0,
               "regressed": 0, "unchanged": 0, "accuracy_unavailable": 0,
               "interpretation_changed": sum(
                   bool(item.get("interpretation_changed")) for item in comparisons
               ),
               "regression_threshold": regression_threshold}
    for item in comparisons:
        key = {"IMPROVED": "improved", "REGRESSION": "regressed",
               "UNCHANGED": "unchanged"}.get(item["status"])
        summary[key or "accuracy_unavailable"] += 1
    if deltas:
        summary["macro_precision_at_k"] = {
            "baseline": sum(before for before, _ in deltas) / len(deltas),
            "current": sum(after for _, after in deltas) / len(deltas),
            "queries_with_supported_precision": len(deltas),
        }
    else:
        summary["macro_precision_at_k"] = {
            "baseline": None, "current": None,
            "status": "UNAVAILABLE: no query has complete top-k judgments in both runs.",
        }
    return {"summary": summary, "queries": comparisons}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--benchmark", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path,
                        help="Compare this run against a saved baseline artifact.")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--regression-threshold", type=float, default=0.05,
                        help="Absolute precision@k drop that marks a regression.")
    parser.add_argument("--limit", type=int,
                        help="Run only the first N benchmark entries.")
    args = parser.parse_args()

    benchmark = _load_json(args.benchmark)
    entries = benchmark["queries"][:args.limit] if args.limit else benchmark["queries"]
    run = {"run_id": datetime.now(timezone.utc).isoformat(),
           "base_url": args.url, "queries": []}
    for index, entry in enumerate(entries, start=1):
        print(f"[{index}/{len(entries)}] {entry['id']}: {entry['query']}", flush=True)
        result = _run_one(args.url, entry, args.timeout)
        run["queries"].append(result)
        status = f"{result['result_count']} results, {result['latency_seconds']:.2f}s"
        if result.get("error"):
            status = f"ERROR: {result['error']}"
        print(f"    {status}", flush=True)

    output_path = args.output or RUNS_DIR / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"Run saved: {output_path}")

    if args.compare:
        report = compare_runs(benchmark, _load_json(args.compare), run,
                              args.regression_threshold)
        report_path = output_path.with_name(output_path.stem + "-comparison.json")
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report["summary"], indent=2))
        for item in report["queries"]:
            interpretation = " (query interpretation changed)" if item.get("interpretation_changed") else ""
            print(f"{item['query_id']}: {item['status']}{interpretation}")
        print(f"Comparison saved: {report_path}")
    else:
        unavailable = sum(not entry.get("ground_truth", {}).get("candidates")
                          for entry in entries)
        print(f"Accuracy metrics unavailable for {unavailable}/{len(entries)} queries: no ground truth.")
        for item in run["queries"]:
            shadow = item.get("shadow_comparison")
            if shadow is None:
                continue
            before = shadow["baseline_result_ids"]
            after = shadow["current_result_ids"]
            delta = shadow
            changed = bool(delta["added"] or delta["removed"]
                           or delta["common_candidate_order_changed"])
            print(
                f"{item['query_id']}: shadow baseline {len(before)} -> current {len(after)}; "
                f"added={len(delta['added'])}, removed={len(delta['removed'])}, "
                f"common_order_changed={delta['common_candidate_order_changed']}; "
                f"accuracy=UNAVAILABLE; result_set_changed={changed}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
