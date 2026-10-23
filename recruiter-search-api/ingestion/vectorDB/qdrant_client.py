from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models


QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "candidate_evidence_hybrid"
DENSE_VECTOR_SIZE = 384

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"


client = QdrantClient(
    url=QDRANT_URL
)


def create_collection() -> None:

    collections = (
        client.get_collections()
        .collections
    )

    if any(
        collection.name == COLLECTION_NAME
        for collection in collections
    ):
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: (
                models.VectorParams(
                    size=DENSE_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                )
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: (
                models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            )
        },
    )


def upsert_evidence(
    candidate_id: int,
    chunk_id: int,
    chunk_type: str,
    section: str,
    text: str,
    vector: list[float],
    metadata: dict | None = None,
) -> None:

    create_collection()

    point_id = str(
        uuid5(
            NAMESPACE_URL,
            f"geniehire:{candidate_id}:{chunk_id}",
        )
    )

    payload = {
        "candidate_id": candidate_id,
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "section": section,
        "text": text,
    }

    if metadata:
        payload.update(
            {
                key: value
                for key, value in metadata.items()
                if value is not None
            }
        )

    point = models.PointStruct(
        id=point_id,
        vector={
            DENSE_VECTOR_NAME: vector,
            SPARSE_VECTOR_NAME: (
                models.Document(
                    text=text,
                    model="Qdrant/bm25",
                )
            ),
        },
        payload=payload,
    )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
    )