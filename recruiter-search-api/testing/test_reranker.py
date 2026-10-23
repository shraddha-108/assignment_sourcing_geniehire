from intelligence.reranker import rerank


query = "candidate with RAG experience"


candidates = [
    {
        "candidate_id": 1,
        "text": "Built a production RAG pipeline using Qdrant, LangChain and OpenAI.",
    },
    {
        "candidate_id": 2,
        "text": "Developed REST APIs using FastAPI and PostgreSQL.",
    },
    {
        "candidate_id": 3,
        "text": "Worked on machine learning models and data preprocessing.",
    },
]


results = rerank(query, candidates)


for result in results:
    print(
        result["candidate_id"],
        result["reranker_score"],
        result["text"],
    )

