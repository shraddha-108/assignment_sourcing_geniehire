from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "candidate_evidence"
VECTOR_SIZE = 384


client = QdrantClient(
    url=QDRANT_URL
)


def create_collection() -> None:
    collections = client.get_collections().collections

    if any(
        collection.name == COLLECTION_NAME
        for collection in collections
    ):
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )


def upsert_evidence(
    candidate_id: int,
    chunk_id: int,
    chunk_type: str,
    section: str,
    text: str,
    vector: list[float],
) -> None:

    create_collection()

    point_id = str(
        uuid5(
            NAMESPACE_URL,
            f"geniehire:{candidate_id}:{chunk_id}",
        )
    )

    point = PointStruct(
        id=point_id,
        vector=vector,
        payload={
            "candidate_id": candidate_id,
            "chunk_id": chunk_id,
            "chunk_type": chunk_type,
            "section": section,
            "text": text,
        },
    )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
    )