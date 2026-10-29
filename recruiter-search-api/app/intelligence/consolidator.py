from collections import defaultdict
import os
import re


MAX_EVIDENCE_PER_CANDIDATE = max(1, int(os.getenv("MAX_EVIDENCE_PER_CANDIDATE", "3")))


def consolidate_semantic_evidence(
    evidence: list[dict],
) -> list[dict]:
    """
    Convert multiple Qdrant evidence chunks into
    one candidate-level object.

    Example:

        candidate 1
            project chunk
            experience chunk
            project chunk

    becomes:

        candidate 1
            evidence = [...]
            semantic_score = strongest evidence score
    """

    grouped = defaultdict(list)

    for item in evidence:

        candidate_id = item.get(
            "candidate_id"
        )

        if candidate_id is None:
            continue

        grouped[candidate_id].append(
            item
        )

    results = []

    for candidate_id, items in grouped.items():

        items = sorted(
            items,
            key=lambda item: (
                float(item.get("reranker_score", 0.0)),
                float(item.get("retrieval_score", 0.0)),
            ),
            reverse=True,
        )

        # Keep only distinct, strongest passages. Resume chunks can overlap,
        # and duplicate passages should not inflate a candidate's evidence.
        distinct_items = []
        seen_evidence_ids = set()
        seen_texts = set()

        for item in items:
            text_key = re.sub(
                r"\s+",
                " ",
                str(item.get("text") or "").strip().lower(),
            )
            evidence_key = item.get("evidence_id")

            if (
                not text_key
                or text_key in seen_texts
                or (
                    evidence_key is not None
                    and evidence_key in seen_evidence_ids
                )
            ):
                continue

            seen_texts.add(text_key)
            if evidence_key is not None:
                seen_evidence_ids.add(evidence_key)
            distinct_items.append(item)

            if len(distinct_items) >= MAX_EVIDENCE_PER_CANDIDATE:
                break

        items = distinct_items

        if not items:
            continue

        best_score = float(
            items[0].get(
                "reranker_score",
                0.0,
            )
        )

        results.append(
            {
                "candidate_id": candidate_id,
                "evidence": items,
                "semantic_score": best_score,
            }
        )

    results.sort(
        key=lambda item: float(
            item.get(
                "semantic_score",
                0.0,
            )
        ),
        reverse=True,
    )

    return results
