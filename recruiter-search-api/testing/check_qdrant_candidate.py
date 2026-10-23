from ingestion.vectorDB.qdrant_client import client, COLLECTION_NAME


results = client.scroll(
    collection_name=COLLECTION_NAME,
    scroll_filter={
        "must": [
            {
                "key": "candidate_id",
                "match": {
                    "value": 5
                }
            }
        ]
    },
    limit=100,
    with_payload=True,
    with_vectors=False,
)

points = results[0]

print(f"\nFound {len(points)} points for candidate 5\n")

for point in sorted(
    points,
    key=lambda x: x.payload.get("chunk_id", 0)
):
    print("=" * 70)
    print(f"chunk_id:   {point.payload.get('chunk_id')}")
    print(f"chunk_type: {point.payload.get('chunk_type')}")
    print(f"section:    {point.payload.get('section')}")
    print(f"text:       {point.payload.get('text')}")