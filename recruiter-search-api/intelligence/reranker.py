from sentence_transformers import CrossEncoder


MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

reranker = CrossEncoder(MODEL_NAME)


def rerank_evidence(
    query: str,
    evidence: list[dict],
) -> list[dict]:
    """
    Rerank individual evidence chunks against the recruiter query.

    The CrossEncoder score represents relevance between the query
    and the evidence text. It is NOT a candidate qualification
    probability.
    """

    if not evidence:
        return []

    pairs = [
        (
            query,
            item.get("text", ""),
        )
        for item in evidence
    ]

    scores = reranker.predict(pairs)

    reranked = []

    for item, score in zip(
        evidence,
        scores,
    ):
        result = dict(item)

        result["reranker_score"] = float(score)

        reranked.append(result)

    reranked.sort(
        key=lambda item: item["reranker_score"],
        reverse=True,
    )

    return reranked


def rerank(
    query: str,
    candidates: list[dict],
) -> list[dict]:
    """
    Backward-compatible candidate reranking.

    This function is retained for callers that still pass
    candidate-level evidence. New retrieval flow should use
    rerank_evidence() before candidate consolidation.
    """

    if not candidates:
        return []

    evidence = []

    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")

        for item in candidate.get("evidence", []):
            evidence_item = dict(item)
            evidence_item["candidate_id"] = candidate_id
            evidence.append(evidence_item)

    reranked_evidence = rerank_evidence(
        query=query,
        evidence=evidence,
    )

    grouped = {}

    for item in reranked_evidence:
        candidate_id = item.get("candidate_id")

        if candidate_id is None:
            continue

        grouped.setdefault(
            candidate_id,
            [],
        ).append(item)

    results = []

    for candidate_id, candidate_evidence in grouped.items():
        results.append(
            {
                "candidate_id": candidate_id,
                "evidence": candidate_evidence,
                "reranker_score": candidate_evidence[0][
                    "reranker_score"
                ],
            }
        )

    results.sort(
        key=lambda item: item["reranker_score"],
        reverse=True,
    )

    return results