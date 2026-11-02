import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "evaluation" / "runs"
GOLDEN_PATH = ROOT / "evaluation" / "datasets" / "golden_queries.json"
GROUND_TRUTH_PATH = ROOT / "evaluation" / "datasets" / "ground_truth.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def resolve_run(label, supplied_path=None):
    if supplied_path:
        path = Path(supplied_path)
        if not path.is_absolute():
            path = ROOT / path

        if not (path / "summary.json").exists():
            raise FileNotFoundError(
                f"Run summary not found in: {path}"
            )
        return path

    parent = RUNS_DIR / label

    if not parent.exists():
        raise FileNotFoundError(f"Run directory not found: {parent}")

    folders = [
        folder for folder in parent.iterdir()
        if folder.is_dir() and (folder / "summary.json").exists()
    ]

    if not folders:
        raise FileNotFoundError(
            f"No completed {label} run found in {parent}"
        )

    return max(
        folders,
        key=lambda folder: (folder / "summary.json").stat().st_mtime,
    )


def load_judgments(ground_truth_data):
    judgments = {}

    for query in ground_truth_data["queries"]:
        query_id = query["query_id"]
        gt = query.get("ground_truth") or {}

        candidate_judgments = gt.get("candidate_judgments") or []

        labels = {}
        for item in candidate_judgments:
            candidate_id = item.get("candidate_id")
            relevance = item.get("relevance")

            if candidate_id is None or relevance not in (0, 1, 2):
                continue

            labels[str(candidate_id)] = relevance

        judgments[query_id] = {
            "labels": labels,
            "pool_scope": gt.get("judgment_pool_scope"),
        }

    return judgments


def load_query_run(run_dir, query_id):
    path = run_dir / f"{query_id}.json"

    if not path.exists():
        return {
            "exists": False,
            "query_id": query_id,
            "route": None,
            "status_code": None,
            "latency_seconds": None,
            "returned_count": 0,
            "candidate_ids": [],
            "relevance_counts": {"2": 0, "1": 0, "0": 0},
            "judged_count": 0,
            "unjudged_count": 0,
            "unjudged_candidate_ids": [],
            "strict_precision": None,
            "relaxed_precision": None,
            "false_positive_rate": None,
            "judgment_coverage": None,
        }

    record = read_json(path)
    response = record.get("response") or {}
    results = response.get("results") or []

    route = record.get("route") or response.get("route")

    candidate_ids = []
    relevance_counts = {"2": 0, "1": 0, "0": 0}
    unjudged_ids = []
    judged_count = 0

    labels = CURRENT_JUDGMENTS.get(query_id, {}).get("labels", {})

    for candidate in results:
        candidate_id = candidate.get("candidate_id")
        if candidate_id is None:
            candidate_id = candidate.get("id")

        if candidate_id is None:
            candidate_ids.append(None)
            unjudged_ids.append(None)
            continue

        candidate_ids.append(str(candidate_id))
        relevance = labels.get(str(candidate_id))

        if relevance is None:
            unjudged_ids.append(str(candidate_id))
            continue

        judged_count += 1
        relevance_counts[str(relevance)] += 1

    total_returned = len(results)
    unjudged_count = total_returned - judged_count

    strict_precision = (
        relevance_counts["2"] / judged_count
        if judged_count else None
    )

    relaxed_precision = (
        (relevance_counts["2"] + relevance_counts["1"]) / judged_count
        if judged_count else None
    )

    false_positive_rate = (
        relevance_counts["0"] / judged_count
        if judged_count else None
    )

    judgment_coverage = (
        judged_count / total_returned
        if total_returned else None
    )

    return {
        "exists": True,
        "query_id": query_id,
        "route": route,
        "status_code": record.get("status_code"),
        "latency_seconds": record.get("latency_seconds"),
        "returned_count": total_returned,
        "candidate_ids": candidate_ids,
        "relevance_counts": relevance_counts,
        "judged_count": judged_count,
        "unjudged_count": unjudged_count,
        "unjudged_candidate_ids": unjudged_ids,
        "strict_precision": strict_precision,
        "relaxed_precision": relaxed_precision,
        "false_positive_rate": false_positive_rate,
        "judgment_coverage": judgment_coverage,
    }


def aggregate(query_results):
    total_returned = sum(q["returned_count"] for q in query_results)
    judged = sum(q["judged_count"] for q in query_results)

    relevance = {
        level: sum(q["relevance_counts"][level] for q in query_results)
        for level in ("2", "1", "0")
    }

    latencies = [
        q["latency_seconds"]
        for q in query_results
        if q["latency_seconds"] is not None
    ]

    return {
        "total_queries": len(query_results),
        "total_returned": total_returned,
        "judged_returned": judged,
        "unjudged_returned": total_returned - judged,
        "relevance_counts": relevance,
        "strict_precision": relevance["2"] / judged if judged else None,
        "relaxed_precision": (
            (relevance["2"] + relevance["1"]) / judged
            if judged else None
        ),
        "false_positive_rate": relevance["0"] / judged if judged else None,
        "judgment_coverage": judged / total_returned if total_returned else None,
        "false_positive_count": relevance["0"],
        "empty_result_queries": sum(
            q["returned_count"] == 0 for q in query_results
        ),
        "average_latency_seconds": mean(latencies) if latencies else None,
    }


def percent(value):
    return "N/A" if value is None else f"{value * 100:.1f}%"


def number(value):
    return "N/A" if value is None else f"{value:.2f}s"


def metric_delta(old, new):
    if old is None or new is None:
        return "N/A"
    return f"{(new - old) * 100:+.1f} pp"


def main():
    parser = argparse.ArgumentParser(
        description="Compare GenieHire baseline and latest evaluation runs."
    )
    parser.add_argument("--baseline-run", help="Optional baseline run folder.")
    parser.add_argument("--latest-run", help="Optional latest run folder.")
    args = parser.parse_args()

    baseline_dir = resolve_run("baseline", args.baseline_run)
    latest_dir = resolve_run("latest", args.latest_run)

    golden_queries = read_json(GOLDEN_PATH)
    ground_truth_data = read_json(GROUND_TRUTH_PATH)

    global CURRENT_JUDGMENTS
    CURRENT_JUDGMENTS = load_judgments(ground_truth_data)

    query_results = []

    for query in golden_queries:
        query_id = query["query_id"]

        baseline = load_query_run(baseline_dir, query_id)
        latest = load_query_run(latest_dir, query_id)

        baseline_ids = {
            item for item in baseline["candidate_ids"] if item is not None
        }
        latest_ids = {
            item for item in latest["candidate_ids"] if item is not None
        }

        query_results.append({
            "query_id": query_id,
            "query": query["query"],
            "baseline": baseline,
            "latest": latest,
            "new_candidate_ids": sorted(latest_ids - baseline_ids),
            "removed_candidate_ids": sorted(baseline_ids - latest_ids),
        })

    baseline_aggregate = aggregate([
        item["baseline"] for item in query_results
    ])
    latest_aggregate = aggregate([
        item["latest"] for item in query_results
    ])

    comparison = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "baseline_run": str(baseline_dir),
        "latest_run": str(latest_dir),
        "judgment_pool_note": (
            "Metrics are calculated only on returned candidates with human "
            "judgments. Unjudged candidates are not treated as irrelevant. "
            "Full recall cannot be calculated from a returned-top-10-only "
            "judgment pool."
        ),
        "baseline_metrics": baseline_aggregate,
        "latest_metrics": latest_aggregate,
        "queries": query_results,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = RUNS_DIR / "comparisons" / timestamp
    report_dir.mkdir(parents=True, exist_ok=False)

    save_json(report_dir / "comparison.json", comparison)

    lines = [
        "# GenieHire Evaluation Comparison",
        "",
        f"- Baseline: `{baseline_dir.name}`",
        f"- Latest: `{latest_dir.name}`",
        "",
        "## Overall metrics",
        "",
        "| Metric | Baseline | Latest |",
        "|---|---:|---:|",
        f"| Strict precision (relevance 2) | {percent(baseline_aggregate['strict_precision'])} | {percent(latest_aggregate['strict_precision'])} |",
        f"| Relaxed precision (relevance 1 or 2) | {percent(baseline_aggregate['relaxed_precision'])} | {percent(latest_aggregate['relaxed_precision'])} |",
        f"| False positives (relevance 0) | {baseline_aggregate['false_positive_count']} | {latest_aggregate['false_positive_count']} |",
        f"| Judgment coverage | {percent(baseline_aggregate['judgment_coverage'])} | {percent(latest_aggregate['judgment_coverage'])} |",
        f"| Candidates returned | {baseline_aggregate['total_returned']} | {latest_aggregate['total_returned']} |",
        f"| Empty-result queries | {baseline_aggregate['empty_result_queries']} | {latest_aggregate['empty_result_queries']} |",
        f"| Average latency | {number(baseline_aggregate['average_latency_seconds'])} | {number(latest_aggregate['average_latency_seconds'])} |",
        "",
        "## Per-query comparison",
        "",
        "| Query | Route (old → new) | Results (old → new) | Strict P (old → new) | Relaxed P (old → new) | FP (old → new) | Latency (old → new) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]

    for item in query_results:
        old = item["baseline"]
        new = item["latest"]

        old_fp = old["relevance_counts"]["0"]
        new_fp = new["relevance_counts"]["0"]

        lines.append(
            f"| {item['query_id']} "
            f"| {old['route'] or 'N/A'} → {new['route'] or 'N/A'} "
            f"| {old['returned_count']} → {new['returned_count']} "
            f"| {percent(old['strict_precision'])} → {percent(new['strict_precision'])} "
            f"| {percent(old['relaxed_precision'])} → {percent(new['relaxed_precision'])} "
            f"| {old_fp} → {new_fp} "
            f"| {number(old['latency_seconds'])} → {number(new['latency_seconds'])} |"
        )

    lines.extend([
        "",
        "## Candidate changes",
        "",
    ])

    for item in query_results:
        lines.append(f"### {item['query_id']}")
        lines.append(f"- Newly returned candidate IDs: {item['new_candidate_ids'] or 'None'}")
        lines.append(f"- No longer returned candidate IDs: {item['removed_candidate_ids'] or 'None'}")
        lines.append(
            f"- Latest unjudged candidate IDs: "
            f"{item['latest']['unjudged_candidate_ids'] or 'None'}"
        )
        lines.append("")

    lines.extend([
        "## Interpretation notes",
        "",
        "- Strict precision counts relevance-2 candidates among judged returned candidates.",
        "- Relaxed precision counts relevance-1 and relevance-2 candidates among judged returned candidates.",
        "- Relevance-0 candidates are counted as false positives.",
        "- Judgment coverage shows what fraction of returned candidates have human labels.",
        "- Unjudged candidates are excluded from precision calculations, not assumed irrelevant.",
        "- Full recall and false-negative rate cannot be established from a returned-top-10-only judgment pool.",
        "",
    ])

    report_text = "\n".join(lines)
    (report_dir / "comparison.md").write_text(
        report_text,
        encoding="utf-8",
    )

    print("\n========== GENIEHIRE COMPARISON ==========\n")
    print(f"Baseline: {baseline_dir}")
    print(f"Latest:   {latest_dir}\n")
    print(
        f"{'METRIC':36} {'BASELINE':>12} {'LATEST':>12}"
    )
    print("-" * 62)

    metrics = [
        ("Strict precision", "strict_precision", percent),
        ("Relaxed precision", "relaxed_precision", percent),
        ("Judgment coverage", "judgment_coverage", percent),
        ("Average latency", "average_latency_seconds", number),
    ]

    for label, key, formatter in metrics:
        print(
            f"{label:36} "
            f"{formatter(baseline_aggregate[key]):>12} "
            f"{formatter(latest_aggregate[key]):>12}"
        )

    print(f"\nReports saved to: {report_dir}")
    print("  - comparison.md")
    print("  - comparison.json")


if __name__ == "__main__":
    CURRENT_JUDGMENTS = {}
    main()
