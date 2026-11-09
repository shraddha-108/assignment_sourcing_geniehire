from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"


model = SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """
    Convert text into a dense semantic embedding.
    """

    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    vector = model.encode(
        text,
        normalize_embeddings=True,
    )

    return vector.tolist()