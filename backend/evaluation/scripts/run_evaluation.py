import argparse
import json
import urllib.error
import urllib.request

from datetime import datetime
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "evaluation" / "datasets" / "golden_queries.json"
RUNS_DIR = ROOT / "evaluation" / "runs"


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def send_search_request(base_url, query, timeout):
    url = f"{base_url.rstrip('/')}/search"

    body = json.dumps({
        "query": query,
        "debug": True,
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = perf_counter()

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            raw_body = response.read().decode("utf-8")

    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw_body = exc.read().decode("utf-8", errors="replace")

    except Exception as exc:
        return {
            "status_code": None,
            "latency_seconds": round(perf_counter() - started, 4),
            "response": None,
            "request_error": str(exc),
        }

    latency = round(perf_counter() - started, 4)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        payload = {"raw_response": raw_body}

    return {
        "status_code": status_code,
        "latency_seconds": latency,
        "response": payload,
        "request_error": None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run GenieHire golden-query evaluation."
    )

    parser.add_argument(
        "--label",
        choices=["baseline", "latest"],
        default="baseline",
        help="Evaluation run category.",
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running GenieHire API.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Maximum seconds to wait for each query.",
    )

    args = parser.parse_args()

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Golden dataset not found: {DATASET_PATH}"
        )

    queries = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )

    if not isinstance(queries, list) or not queries:
        raise ValueError("Golden query dataset must be a non-empty list.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RUNS_DIR / args.label / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    print(f"\nEvaluation label : {args.label}")
    print(f"Run ID           : {run_id}")
    print(f"API              : {args.base_url}")
    print(f"Queries          : {len(queries)}")
    print(f"Output           : {output_dir}\n")

    summary_records = []

    for index, item in enumerate(queries, start=1):
        query_id = item["query_id"]
        query = item["query"]

        print(f"[{index}/{len(queries)}] Running {query_id}: {query}")

        result = send_search_request(
            args.base_url,
            query,
            args.timeout,
        )

        response = result["response"]
        response = response if isinstance(response, dict) else {}

        candidates = response.get("results")
        returned_count = len(candidates) if isinstance(candidates, list) else 0

        record = {
            "query_id": query_id,
            "benchmark_query": query,
            "endpoint": f"{args.base_url.rstrip('/')}/search",
            "executed_at": datetime.now().astimezone().isoformat(),
            "status_code": result["status_code"],
            "latency_seconds": result["latency_seconds"],
            "request_error": result["request_error"],
            "valid": response.get("valid"),
            "route": response.get("route"),
            "search_id": response.get("search_id"),
            "returned_count": returned_count,
            "response": result["response"],
        }

        save_json(output_dir / f"{query_id}.json", record)

        successful = (
            result["status_code"] is not None
            and 200 <= result["status_code"] < 300
            and result["request_error"] is None
        )

        summary_records.append({
            "query_id": query_id,
            "query": query,
            "status_code": result["status_code"],
            "successful_request": successful,
            "valid": response.get("valid"),
            "route": response.get("route"),
            "returned_count": returned_count,
            "latency_seconds": result["latency_seconds"],
            "search_id": response.get("search_id"),
        })

        print(
            f"    Status: {result['status_code']} | "
            f"Route: {response.get('route')} | "
            f"Candidates: {returned_count} | "
            f"Latency: {result['latency_seconds']}s"
        )

        if result["request_error"]:
            print(f"    ERROR: {result['request_error']}")

    successful_count = sum(
        1 for record in summary_records
        if record["successful_request"]
    )

    summary = {
        "evaluation_label": args.label,
        "run_id": run_id,
        "started_or_completed_at": datetime.now().astimezone().isoformat(),
        "api_base_url": args.base_url,
        "debug_enabled": True,
        "total_queries": len(queries),
        "successful_requests": successful_count,
        "failed_requests": len(queries) - successful_count,
        "queries": summary_records,
    }

    save_json(output_dir / "summary.json", summary)

    print("\n========== EVALUATION COMPLETE ==========")
    print(f"Total queries      : {len(queries)}")
    print(f"Successful requests: {successful_count}")
    print(f"Failed requests    : {len(queries) - successful_count}")
    print(f"Saved to           : {output_dir}")


if __name__ == "__main__":
    main()
