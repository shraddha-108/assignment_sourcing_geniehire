from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"

model = SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    vector = model.encode(
        text,
        normalize_embeddings=True,
    )

    return vector.tolist()


def embedding_dimension() -> int:
    return model.get_sentence_embedding_dimension()