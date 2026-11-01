
from langchain_ollama import ChatOllama

from app.ingestion.schemas.classification import (
    ResumeClassification,
)


MODEL_NAME = "qwen3:4b"

OLLAMA_BASE_URL = "http://localhost:11434"

CLASSIFICATION_VERSION = "qwen3:4b-domain-v1"


SYSTEM_PROMPT = """
You are a professional resume-domain classification system.

Your task is to identify the candidate's primary professional domain.

Choose exactly ONE domain:

1. TECHNICAL:
   Software engineering, IT, AI/ML, data science,
   cloud, DevOps, cybersecurity, QA, infrastructure.

2. SALES:
   Business development, sales, account executive,
   prospecting, lead generation, revenue generation,
   account management.

3. MARKETING:
   Digital marketing, SEO, SEM, content marketing,
   social media, branding, campaigns, performance marketing.

4. HR:
   Recruitment, talent acquisition, human resources,
   employee relations, people operations, learning and development.

5. FINANCE:
   Accounting, auditing, taxation, banking,
   financial planning, financial analysis, treasury.

6. OPERATIONS:
   Supply chain, logistics, procurement,
   manufacturing, business operations.

7. CUSTOMER_SUCCESS:
   Customer support, customer success,
   onboarding, customer retention, implementation support.

8. PRODUCT:
   Product management, product strategy,
   product roadmap, product operations, user research.

9. GENERAL:
   Use when no single domain clearly represents
   the candidate's professional background.

CLASSIFICATION RULES:

- Prioritize actual work responsibilities and experience.
- Consider job titles and professional summaries.
- Projects are important supporting evidence.
- Skills are supporting evidence, not the sole deciding factor.
- Do not classify someone as technical merely because
  they mention Python, SQL, or another technical skill.
- Consider the candidate's overall professional background.
- Choose one primary domain even if the candidate
  has experience across multiple domains.
- Use GENERAL when evidence is insufficient.
- Do not invent information.

Return only the required structured output.
"""


def classify_resume(text: str) -> ResumeClassification:
    """
    Classify a resume using Qwen3:4B through local Ollama.

    Input:
        Selected professional information from the resume.

    Output:
        Primary domain and model-estimated confidence.
    """

    if not text or not text.strip():
        raise ValueError(
            "Classification input cannot be empty."
        )

    llm = ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )

    structured_llm = llm.with_structured_output(
        ResumeClassification,
        method="json_schema",
    )

    result = structured_llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                f"Classify this resume:\n\n{text}",
            ),
        ]
    )

    if result is None:
        raise ValueError(
            "Classifier returned no result."
        )

    return result
