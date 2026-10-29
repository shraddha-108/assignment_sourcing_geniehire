import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

load_dotenv(override=True)


QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://localhost:6333",
)

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION",
    "candidate_evidence_hybrid",
)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"

DENSE_VECTOR_SIZE = 384
_CANDIDATE_ID_INDEX_READY = False
_COLLECTION_READY = False


client = QdrantClient(
    url=QDRANT_URL,
)


def ensure_collection() -> None:
    """
    Create the hybrid Qdrant collection if it does not exist.

    The collection contains:

    1. dense -> BGE embeddings
    2. bm25  -> sparse BM25 vectors
    """

    global _CANDIDATE_ID_INDEX_READY, _COLLECTION_READY
    if _COLLECTION_READY:
        return
    collections = client.get_collections()

    exists = any(
        collection.name == COLLECTION_NAME
        for collection in collections.collections
    )

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=DENSE_VECTOR_SIZE,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams()
            },
        )

    if not _CANDIDATE_ID_INDEX_READY:
        collection = client.get_collection(COLLECTION_NAME)
        if "candidate_id" not in (collection.payload_schema or {}):
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="candidate_id",
                field_schema=PayloadSchemaType.INTEGER,
            )
        _CANDIDATE_ID_INDEX_READY = True
    _COLLECTION_READY = True
