from ingestion.vectorDB.qdrant_client import (
    client,
    COLLECTION_NAME as HYBRID_COLLECTION,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)
from qdrant_client import models


OLD_COLLECTION = "candidate_evidence"


def migrate_points() -> None:

    source_offset = None
    total = 0

    while True:

        points, source_offset = client.scroll(
            collection_name=OLD_COLLECTION,
            limit=100,
            offset=source_offset,
            with_payload=True,
            with_vectors=True,
        )

        if not points:
            break

        migrated_points = []

        for point in points:

            payload = point.payload or {}
            text = payload.get("text", "")

            if not text:
                continue

            dense_vector = point.vector

            if isinstance(dense_vector, dict):
                dense_vector = dense_vector.get(
                    ""
                )

            if dense_vector is None:
                continue

            migrated_points.append(
                models.PointStruct(
                    id=point.id,
                    vector={
                        DENSE_VECTOR_NAME: dense_vector,
                        SPARSE_VECTOR_NAME: models.Document(
                            text=text,
                            model="Qdrant/bm25",
                        ),
                    },
                    payload=payload,
                )
            )

        if migrated_points:

            client.upsert(
                collection_name=HYBRID_COLLECTION,
                points=migrated_points,
            )

            total += len(migrated_points)

            print(
                f"Migrated {total} points..."
            )

        if source_offset is None:
            break

    print(
        f"Migration complete. "
        f"Total points: {total}"
    )


if __name__ == "__main__":
    migrate_points()