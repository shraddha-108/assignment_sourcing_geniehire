from langchain_huggingface import HuggingFaceEmbeddings


MODEL_NAME = "BAAI/bge-small-en-v1.5"


embeddings = HuggingFaceEmbeddings(
    model_name=MODEL_NAME,
    encode_kwargs={
        "normalize_embeddings": True,
    },
)


def embed_text(text: str) -> list[float]:
    return embeddings.embed_query(text)


def embedding_dimension() -> int:
    return embeddings.client.get_sentence_embedding_dimension()