from fastembed import SparseTextEmbedding
from qdrant_client.models import SparseVector


MODEL_NAME = "Qdrant/bm25"


model = SparseTextEmbedding(
    model_name=MODEL_NAME,
)


def bm25_document(text: str) -> SparseVector:
    """
    Convert document text into a BM25 sparse vector.

    Used while indexing resume evidence.
    """

    if not text or not text.strip():
        raise ValueError("Cannot create BM25 vector from empty text.")

    embedding = next(
        model.embed([text])
    )

    return SparseVector(
        indices=embedding.indices.tolist(),
        values=embedding.values.tolist(),
    )


def bm25_query(text: str) -> SparseVector:
    """
    Convert a search query into a BM25 sparse vector.

    Used during retrieval.
    """

    if not text or not text.strip():
        raise ValueError("Cannot create BM25 query from empty text.")

    embedding = next(
        model.query_embed([text])
    )

    return SparseVector(
        indices=embedding.indices.tolist(),
        values=embedding.values.tolist(),
    )