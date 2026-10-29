import os

from sentence_transformers import CrossEncoder


MODEL_NAME = os.getenv(
    "RERANKER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)
RERANK_BATCH_SIZE = max(1, int(os.getenv("RERANK_BATCH_SIZE", "64")))
MAX_CHUNK_RERANK_PAIRS = max(1, int(os.getenv("MAX_CHUNK_RERANK_PAIRS", "160")))
MAX_CANDIDATE_VALIDATION_PAIRS = max(
    1, int(os.getenv("MAX_CANDIDATE_VALIDATION_PAIRS", "64"))
)
# Raw CrossEncoder relevance score threshold; this is not a probability.
CANDIDATE_VALIDATION_MIN_SCORE = float(
    os.getenv("CANDIDATE_VALIDATION_MIN_SCORE", "0.0")
)

_reranker = None


def _get_reranker() -> CrossEncoder:

    global _reranker

    if _reranker is None:

        _reranker = CrossEncoder(
            MODEL_NAME,
            max_length=384,
        )

    return _reranker


def rerank_evidence(
    query: str,
    evidence: list[dict],
) -> list[dict]:
    """
    Rerank retrieved evidence using CrossEncoder.

    CrossEncoder provides relevance scoring.
    It does NOT decide candidate qualification.
    """

    if not evidence:
        return []

    model = _get_reranker()

    pairs = []
    pair_indexes = {}
    evidence_pair_indexes = []

    for item in evidence:

        text = str(
            item.get("text")
            or ""
        ).strip()

        evidence_query = str(item.get("reranker_query") or query).strip()
        pair = (evidence_query, text)
        pair_index = pair_indexes.get(pair)
        if pair_index is None:
            pair_index = len(pairs)
            pair_indexes[pair] = pair_index
            pairs.append(pair)
        evidence_pair_indexes.append(pair_index)

    scores = model.predict(
        pairs,
        batch_size=RERANK_BATCH_SIZE,
        show_progress_bar=False,
    )

    results = []

    for item, pair_index in zip(evidence, evidence_pair_indexes):

        result = dict(item)

        result[
            "reranker_score"
        ] = float(scores[pair_index])

        results.append(
            result
        )

    results.sort(
        key=lambda item: float(
            item.get(
                "reranker_score",
                0.0,
            )
        ),
        reverse=True,
    )

    return results
