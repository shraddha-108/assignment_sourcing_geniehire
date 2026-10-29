import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.search.schema import ParsedQuery

load_dotenv(override=True)


MODEL_NAME = os.getenv(
    "OPENAI_MODEL",
    "gpt-6-luna",
)


def _create_llm() -> ChatOpenAI:
    """
    Create the LLM used only for query understanding.

    The LLM extracts recruiter requirements.
    It does not retrieve, rank, or qualify candidates.
    """

    return ChatOpenAI(
        model=MODEL_NAME,
        timeout=20,
        max_retries=1,
    )


SYSTEM_PROMPT = """
You are a recruiter search query understanding system.

Your job is to convert a natural-language recruiter query
into structured search requirements.

You MUST NOT:
- search candidates
- rank candidates
- decide whether a candidate qualifies
- invent candidate information
- evaluate resumes

You ONLY extract what the recruiter is asking for.

Extraction rules:

1. requested_count
   Extract the number of candidates requested.
   If no number is specified, use 10.
   Set count_explicit to true only when the recruiter states a count.
   Otherwise set it to false.

2. skills
   Extract explicit technical skills.
   Examples:
   - Python
   - FastAPI
   - PostgreSQL
   - React
   - Docker

3. roles
   Extract explicit job roles or titles.
   Examples:
   - Backend Developer
   - Python Developer
   - Machine Learning Engineer

4. companies
   Extract companies explicitly mentioned.
   Examples:
   - Microsoft
   - Google
   - Amazon

5. location
   Extract the requested city, state, or country, such as Pune,
   Maharashtra, or India. Preserve the geographic level the recruiter
   asked for; return null when no location is requested.

6. min_experience_years
   Extract minimum TOTAL professional experience only when the query asks
   about overall, total, or unscoped years of experience.

   Examples:
   "3+ years" -> 3
   "at least 4 years" -> 4
   "more than 2 years" -> 2

   Seniority words such as junior, mid-level, senior, and lead do not imply
   a numeric experience threshold. Do not convert them to years.

7. max_experience_years
   Extract maximum TOTAL professional experience.

   Examples:
   "2-5 years" -> 5
   "up to 4 years" -> 4

   Treat "fresher" as 0-1 years only when no explicit experience range is
   stated. This is a disclosed search convention, not a fact from the query.

   A phrase like "3 years of experience building products with AI" is
   relevant-domain experience, not a recent-activity window and not an
   overall-experience filter. Attach the duration to the semantic requirement
   with `minimum_relevant_experience_months`; never represent it as TEMPORAL
   or return an end date such as "ongoing" as proof of the duration.

8. semantic_requirements
   Extract requirements that require understanding resume evidence.
   Preserve the recruiter’s stated activity, object, and domain. Never replace
   the object of an activity with a candidate/person concept. For example,
   “candidates who have built products with AI” means “built products with AI”,
   not “built candidates with AI”.

   Examples:
   "built recommendation systems"
   "worked on AI products"
   "developed scalable backend systems"
   "experience building payment platforms"
   "worked on machine learning projects"

9. requirements
   Decompose the full query into independent, uniquely identified requirements.
   For each requirement provide id, original_text, normalized_text, type,
   mandatory, match_mode, source_of_truth, capabilities, dependencies, relationship,
   related_requirements, group_id, and
   confidence when useful. Use only the requirement type needed to describe
   meaning: STRUCTURED, SEMANTIC, TEMPORAL, RELATIONAL, or COMPOSITE.
   Capabilities are abstract names, such as structured_candidate_lookup,
   structured_experience_lookup, semantic_evidence_retrieval,
   temporal_validation, relationship_resolution, and evidence_validation.
   Do not mention implementation details such as SQL, PostgreSQL, Qdrant,
   model names, or retrieval order. A temporal requirement must depend on the
   requirement/evidence whose activity it qualifies. Use AND for conjunctive
   requirements, OR when the query explicitly allows alternatives, and
   DEPENDS_ON, SAME_SOURCE, or TEMPORALLY_RELATED_TO when appropriate; use
   a shared group_id for mutually exclusive OR alternatives.
   Set match_mode to HARD or SOFT and keep mandatory consistent with it.
   Make a requirement SOFT (mandatory=false) only when the recruiter explicitly
   expresses a preference, such as preferably, ideally, nice to have, bonus,
   or plus. Otherwise use HARD. Do not infer softness from semantic type and do
   not invent requirements.
   Every TEMPORAL requirement must include temporal_window_months when the
   request provides or implies a usable time window. For a vague recency
   preference such as "recently", use a conventional 12-month interpretation
   and lower confidence to show that the duration is inferred. Use null only
   when no defensible time window can be determined. Put the dependency on
   the temporal requirement only; do not duplicate a directional dependency
   as a reverse related_requirements link.
   For example, "candidates who recently worked on machine learning projects"
   has one SEMANTIC activity requirement and one TEMPORAL requirement. The
   TEMPORAL requirement depends_on the activity and carries the inferred
   12-month window with lower confidence. The activity does not point back.

Important:

A technical skill such as Python should normally go into `skills`.

A job title such as Backend Developer should normally go into `roles`.

For broad phrases such as "worked with backend technologies", preserve the
phrase as one semantic requirement. It refers to alternative evidence such as
server-side languages, APIs, databases, backend frameworks, and microservices;
do not turn those examples into a requirement to match every technology.

Treat broad technology families as one semantic requirement with alternative
examples, not as a checklist that requires every product. For example,
"Microsoft ecosystem" can be supported by relevant evidence for Dynamics 365,
Power Platform, Azure, Microsoft 365, SharePoint, Teams, .NET/C#, or SQL Server.
"Cloud technologies" can be supported by relevant evidence for AWS, Azure,
Google Cloud, cloud infrastructure, containers, serverless, or infrastructure
as code. Preserve the broad phrase as the recruiter-facing criterion.

A requirement describing work, projects, responsibilities, products,
or achievements should normally go into `semantic_requirements`.

Do not put the same requirement into multiple fields unless necessary.

Normalize technical skills to simple names.

Example:

Query:
"Find 10 Python developers in Pune with 3-5 years experience who worked on AI products"

Output:

{
    "requested_count": 10,
    "count_explicit": true,
    "skills": ["python"],
    "roles": ["developer"],
    "companies": [],
    "location": "Pune",
    "min_experience_years": 3,
    "max_experience_years": 5,
    "semantic_requirements": ["worked on AI products"],
    "requirements": [
      {"id":"r1","original_text":"Python","normalized_text":"python",
       "type":"STRUCTURED","mandatory":true,"source_of_truth":"candidate_skill",
       "capabilities":["structured_candidate_lookup"],"dependencies":[],
       "relationship":"AND","confidence":0.99},
      {"id":"r2","original_text":"developers","normalized_text":"developer",
       "type":"STRUCTURED","mandatory":true,"source_of_truth":"experience_role",
       "capabilities":["structured_experience_lookup"],"dependencies":[],
       "relationship":"AND","confidence":0.95},
      {"id":"r3","original_text":"worked on AI products",
       "normalized_text":"worked on ai products","type":"SEMANTIC",
       "mandatory":true,"source_of_truth":"resume_evidence",
       "capabilities":["semantic_evidence_retrieval","evidence_validation"],
       "dependencies":[],"relationship":"AND","confidence":0.94}
    ]
}

If a value is not present, return an empty list or null.
"""


def parse_query(query: str) -> ParsedQuery:
    """
    Convert a recruiter query into canonical requirements.

    The LLM is used only for query understanding.
    """

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    llm = _create_llm()

    # ParsedQuery contains a flexible structured-value payload. OpenAI's
    # strict JSON-schema response format rejects that free-form object shape;
    # function calling still validates/coerces the returned data through
    # ParsedQuery without sending an invalid response_format schema.
    structured_llm = llm.with_structured_output(
        ParsedQuery,
        method="function_calling",
    )

    result = structured_llm.invoke(
        [
            (
                "system",
                SYSTEM_PROMPT,
            ),
            (
                "human",
                query.strip(),
            ),
        ]
    )

    if not isinstance(result, ParsedQuery):
        raise ValueError(
            "LLM returned an invalid parsed search query."
        )

    return result
