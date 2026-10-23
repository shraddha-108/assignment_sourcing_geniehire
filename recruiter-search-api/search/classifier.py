import os
import re
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


load_dotenv()


OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-4o-mini",
)

DEFAULT_COUNT = 10
MAX_COUNT = 100


class StructuredRequirements(BaseModel):
    skills: list[str] = Field(default_factory=list)
    role: str | None = None

    recency_months: int | None = None

    recency_scope: Literal[
        "SKILL",
        "SEMANTIC",
        "OVERALL",
        "UNKNOWN",
    ] | None = None

    experience_min_years: float | None = None

    experience_scope: Literal[
        "OVERALL",
        "SKILL",
        "UNKNOWN",
    ] | None = None


class SearchRequirement(BaseModel):
    """
    A recruiter requirement independent of retrieval strategy.

    This describes what must be proven. Retrieval and validation decide where
    the evidence comes from and whether the evidence is sufficient.
    """

    type: Literal[
        "SKILL",
        "ROLE",
        "EXPERIENCE",
        "ACTIVITY",
        "INDUSTRY",
        "OTHER",
    ]

    value: str
    required: bool = True

    operator: Literal[
        "EQ",
        "GTE",
        "LTE",
        "CONTAINS",
        "NOT",
        "PREFERRED",
    ] | None = None

    scope: Literal[
        "OVERALL",
        "SKILL",
        "ROLE",
        "ACTIVITY",
        "PROJECT",
        "UNKNOWN",
    ] | None = None

    recency_months: int | None = None

    # Natural-language description of the evidence to retrieve.
    evidence_query: str | None = None


class SearchIntent(BaseModel):
    requested_count: int | None = None
    count_explicit: bool = False

    # Source-of-truth representation of recruiter requirements.
    requirements: list[SearchRequirement] = Field(default_factory=list)

    # Legacy fields retained for the current pipeline during migration.
    route: Literal[
        "STRUCTURED",
        "SEMANTIC",
        "HYBRID",
    ]

    structured_requirements: StructuredRequirements

    semantic_requirement: str | None = None

    reason: str


def _create_llm() -> ChatOpenAI:

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured."
        )

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=api_key,
        temperature=0,
        max_retries=2,
    )


def _normalize_skills(
    skills: list[str],
    known_skills: list[str],
) -> list[str]:

    known_map = {
        skill.strip().lower(): skill.strip()
        for skill in known_skills
        if skill and skill.strip()
    }

    normalized = []

    for skill in skills:

        if not skill:
            continue

        key = skill.strip().lower()

        if key in known_map:

            canonical = known_map[key]

            if canonical not in normalized:
                normalized.append(canonical)

    return normalized


def _normalize_count(
    requested_count: int | None,
    count_explicit: bool,
) -> tuple[int, bool]:

    if not count_explicit:
        return DEFAULT_COUNT, False

    if requested_count is None:
        return DEFAULT_COUNT, False

    requested_count = max(
        1,
        min(requested_count, MAX_COUNT),
    )

    return requested_count, True


def _contains_phrase(
    text: str,
    phrase: str,
) -> bool:

    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"

    return bool(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
    )


def _has_action_language(
    text: str,
) -> bool:

    action_patterns = [
        r"\bbuilt\b",
        r"\bbuild\b",
        r"\bdeveloped\b",
        r"\bdevelop\b",
        r"\bcreated\b",
        r"\bcreate\b",
        r"\bimplemented\b",
        r"\bimplement\b",
        r"\bdesigned\b",
        r"\bdesign\b",
        r"\bdeployed\b",
        r"\bdeploy\b",
        r"\bintegrated\b",
        r"\bintegrate\b",
        r"\bengineered\b",
        r"\bengineer\b",
        r"\btrained\b",
        r"\btrain\b",
        r"\boptimized\b",
        r"\boptimize\b",
        r"\bmaintained\b",
        r"\bmaintain\b",
        r"\bautomated\b",
        r"\bautomate\b",
        r"\barchitected\b",
        r"\barchitect\b",
        r"\bdelivered\b",
        r"\bdeliver\b",
        r"\bmigrated\b",
        r"\bmigrate\b",
        r"\bscaled\b",
        r"\bscale\b",
        r"\bled\b",
        r"\bmanaged\b",
        r"\bmanage\b",
        r"\bconfigured\b",
        r"\bconfigure\b",
        r"\borchestrated\b",
        r"\borchestrate\b",
        r"\bdebugged\b",
        r"\bdebug\b",
        r"\bmodernized\b",
        r"\bmodernize\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in action_patterns
    )


def _is_generic_semantic_phrase(
    semantic_requirement: str,
) -> bool:

    normalized = (
        semantic_requirement
        .strip()
        .lower()
    )

    generic_phrases = {
        "worked with",
        "experience with",
        "experienced with",
        "used",
        "knowledge of",
        "familiar with",
        "hands-on experience with",
        "proficient in",
        "experience using",
        "skilled in",
        "expert in",
        "strong knowledge of",
        "strong experience with",
    }

    return normalized in generic_phrases


def _is_simple_skill_possession(
    semantic_requirement: str,
    skills: list[str],
) -> bool:

    semantic_text = (
        semantic_requirement
        .strip()
        .lower()
    )

    if not semantic_text:
        return True

    if _has_action_language(
        semantic_text
    ):
        return False

    possession_patterns = [
        "worked with",
        "experience with",
        "experienced with",
        "used",
        "knowledge of",
        "familiar with",
        "hands-on experience with",
        "proficient in",
        "experience using",
        "skilled in",
        "expert in",
        "strong knowledge of",
        "strong experience with",
    ]

    for skill in skills:

        skill_text = (
            skill.strip()
            .lower()
        )

        if not skill_text:
            continue

        for prefix in possession_patterns:

            expected = (
                f"{prefix} {skill_text}"
            )

            if semantic_text == expected:
                return True

    return False


def _repair_semantic_requirement(
    semantic_requirement: str | None,
    skills: list[str],
) -> str | None:

    if not semantic_requirement:
        return None

    semantic_requirement = (
        semantic_requirement
        .strip()
    )

    if not semantic_requirement:
        return None

    if _is_generic_semantic_phrase(
        semantic_requirement
    ):
        return None

    if _is_simple_skill_possession(
        semantic_requirement,
        skills,
    ):
        return None

    return semantic_requirement


def _derive_route(
    structured_requirements: StructuredRequirements,
    semantic_requirement: str | None,
    requirements: list[SearchRequirement],
) -> str:

    has_structured = bool(
        structured_requirements.skills
        or structured_requirements.role
        or structured_requirements.recency_months is not None
        or structured_requirements.experience_min_years is not None
    )

    # These requirement types are not safely represented by the current
    # structured database filters, so they remain semantic until their
    # retrieval/validation logic is implemented.
    has_semantic_requirements = any(
        requirement.type in {
            "ACTIVITY",
            "INDUSTRY",
            "OTHER",
        }
        for requirement in requirements
    )

    has_semantic = bool(
        semantic_requirement
        and semantic_requirement.strip()
    ) or has_semantic_requirements

    if has_structured and has_semantic:
        return "HYBRID"

    if has_structured:
        return "STRUCTURED"

    if has_semantic:
        return "SEMANTIC"

    return "SEMANTIC"


def _normalize_requirements(
    requirements: list[SearchRequirement],
    known_skills: list[str],
) -> list[SearchRequirement]:
    """
    Canonicalize known skills without inventing or expanding them.

    An unknown skill is deliberately kept semantic rather than becoming a
    false structured filter.
    """

    known_map = {
        skill.strip().lower(): skill.strip()
        for skill in known_skills
        if skill and skill.strip()
    }

    normalized: list[SearchRequirement] = []

    for requirement in requirements:
        value = requirement.value.strip()

        if not value:
            continue

        if requirement.type == "SKILL":
            canonical = known_map.get(value.lower())

            if canonical:
                requirement.value = canonical
            else:
                requirement.type = "OTHER"
                requirement.evidence_query = (
                    requirement.evidence_query or value
                )

        requirement.value = value
        normalized.append(requirement)

    return normalized


def _build_legacy_projection(
    requirements: list[SearchRequirement],
) -> tuple[StructuredRequirements, str | None]:
    """
    Project requirements into the current pipeline's legacy fields.

    The requirement list remains the source of truth. This projection exists
    only so the existing retrieval code does not break during migration.
    """

    skills: list[str] = []
    role: str | None = None
    experience_min_years: float | None = None
    experience_scope: str | None = None

    semantic_parts: list[str] = []

    recency_months: int | None = None
    recency_scope: str | None = None

    for requirement in requirements:
        if not requirement.required:
            evidence = (
                requirement.evidence_query
                or requirement.value
            )
            semantic_parts.append(f"{evidence} preferred")
            continue

        if requirement.type == "SKILL":
            if requirement.value not in skills:
                skills.append(requirement.value)

            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "SKILL"

        elif requirement.type == "ROLE":
            role = requirement.value

            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "OVERALL"

        elif requirement.type == "EXPERIENCE":
            try:
                experience_min_years = float(requirement.value)
            except (TypeError, ValueError):
                experience_min_years = None

            if requirement.scope == "SKILL":
                experience_scope = "SKILL"
            elif requirement.scope == "OVERALL":
                experience_scope = "OVERALL"
            else:
                experience_scope = "UNKNOWN"

            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "OVERALL"

        else:
            semantic_parts.append(
                requirement.evidence_query
                or requirement.value
            )

            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "SEMANTIC"

    structured = StructuredRequirements(
        skills=skills,
        role=role,
        recency_months=recency_months,
        recency_scope=recency_scope,
        experience_min_years=experience_min_years,
        experience_scope=experience_scope,
    )

    semantic_requirement = (
        " AND ".join(semantic_parts)
        if semantic_parts
        else None
    )

    return structured, semantic_requirement


def classify_search_intent(
    query: str,
    known_skills: list[str],
) -> SearchIntent:

    query = query.strip()

    skills_text = "\n".join(
        f"- {skill}"
        for skill in known_skills
    )

    prompt = f"""
You are the query-understanding layer for a recruiter candidate search system.

Your ONLY job is to understand the recruiter's natural-language query.

You must NOT:
- retrieve candidates
- rank candidates
- evaluate candidates
- invent candidate information
- invent skills
- infer unstated technologies
- expand broad technology terms into lists of technologies

You must extract:

1. requested_count
2. count_explicit
3. requirements
4. reason

The final route is determined by Python after your response.

The `requirements` list is the source-of-truth description of what the
recruiter wants. Each requirement must describe one independently verifiable
claim. Do not decide whether a candidate satisfies it.

For each requirement:
- `type` identifies the kind of claim.
- `value` contains the requested concept or value.
- `required=true` unless the recruiter explicitly says preferred/optional.
- `operator` represents numeric comparison or explicit NOT/PREFERRED meaning.
- `scope` identifies what the requirement refers to when relevant.
- `recency_months` belongs to the requirement it modifies.
- `evidence_query` preserves the natural-language evidence that should be
  retrieved when the requirement is semantic.

The requirement model is independent of STRUCTURED, SEMANTIC, and HYBRID.
Routing is an execution decision made later.

Examples:

"Python developers"
-> SKILL / Python / required=true

"finance managers with 6 years experience in IT industry"
-> ROLE / finance manager / required=true
-> EXPERIENCE / 6 / operator=GTE / scope=OVERALL / required=true
-> INDUSTRY / IT / required=true /
   evidence_query="worked in the IT industry"

"Python developers who recently built machine learning projects"
-> SKILL / Python / required=true
-> ACTIVITY / built machine learning projects / required=true /
   recency_months=12 / scope=PROJECT /
   evidence_query="built machine learning projects"

IMPORTANT:
A temporal modifier belongs to the requirement it modifies. Do not attach
"recently" to Python merely because Python appears elsewhere in the query.

The legacy structured_requirements and semantic_requirement fields are kept
for compatibility with the current pipeline. They must be consistent with the
requirement list, but the requirement list is the richer representation.

==================================================
REQUIREMENT TYPES
==================================================

Use these requirement types:

- SKILL: one specific known technology or skill.
- ROLE: an explicit job title or role.
- EXPERIENCE: a numeric professional-experience requirement.
- ACTIVITY: an action/work/project requirement such as "built RAG systems".
- INDUSTRY: an industry/context requirement such as "worked in the IT industry".
- OTHER: an explicit requirement that does not safely fit another type.

Do not force a requirement into SKILL merely because one of its words is a
known database skill.

"built machine learning projects"
-> ACTIVITY, not SKILL

"worked in the IT industry"
-> INDUSTRY, not SKILL

"worked with Microsoft ecosystem"
-> OTHER/semantic, not a list of Microsoft skills.

==================================================
TEMPORAL OWNERSHIP
==================================================

Recency must belong to the requirement whose evidence must be recent.

"recent Python experience"
-> SKILL / Python / recency_months=12

"recently built ML projects"
-> ACTIVITY / built ML projects / recency_months=12

"Python developers who recently built ML projects"
-> SKILL / Python
-> ACTIVITY / built ML projects / recency_months=12

Do not use unrelated recent activity to prove that the target requirement was
recent.

==================================================
REQUIREMENT DECOMPOSITION
==================================================

Do not collapse multiple independently testable claims into one semantic
sentence when they can be represented separately.

"finance managers with 6 years experience in IT industry"

must contain:

ROLE / finance manager
EXPERIENCE / 6 / GTE
INDUSTRY / IT

The downstream system will retrieve and validate these claims separately.

==================================================
STRUCTURED REQUIREMENTS
==================================================

Extract only the structured requirements that are explicitly present in the
recruiter's query.

All structured fields are optional.

Supported structured fields:

- skills
- role
- recency_months
- recency_scope
- experience_min_years
- experience_scope

==================================================
SKILLS
==================================================

A structured skill means ONE SPECIFIC skill explicitly required by the recruiter.

Only use a skill if it exists in the database skill list.

Examples:

"Python developers"
-> skills = ["Python"]

"developers with AWS"
-> skills = ["AWS"]

"developers experienced in Python"
-> skills = ["Python"]

"developers who worked with Python"
-> skills = ["Python"]

"developers familiar with React"
-> skills = ["React"]

"developers proficient in PostgreSQL"
-> skills = ["PostgreSQL"]

==================================================
DO NOT INFER RELATED SKILLS
==================================================

Never expand a broad term into related skills.

If the database contains:

Microsoft Azure
Microsoft Dynamics 365
Microsoft Office Suite

and the recruiter says:

"Microsoft ecosystem"

DO NOT output:

Microsoft Azure
Microsoft Dynamics 365
Microsoft Office Suite

Instead:

skills = []
semantic_requirement = "worked with Microsoft ecosystem"

The recruiter must explicitly name a specific skill for it to become structured.

==================================================
SPECIFIC SKILL VS BROAD DOMAIN
==================================================

Specific skill:

"worked with Python"
-> structured

"worked with AWS"
-> structured

"worked with Docker"
-> structured

Broad domain:

"worked with Microsoft ecosystem"
-> semantic

"worked with Microsoft technologies"
-> semantic

"worked with cloud technologies"
-> semantic

"worked with enterprise platforms"
-> semantic

"worked with payment systems"
-> semantic

"worked with distributed systems"
-> semantic

"worked with AI technologies"
-> semantic

"worked with the Microsoft stack"
-> semantic

Broad concepts must remain semantic.

==================================================
ROLE
==================================================

Extract a role or job title when the recruiter specifies one.

Examples:

"backend developers"
-> role = "backend developer"

"data scientists"
-> role = "data scientist"

"finance managers"
-> role = "finance manager"

"senior Python developers"
-> role = "senior Python developer"

"machine learning engineers"
-> role = "machine learning engineer"

Do not invent a role if the query does not specify one.

Do not treat a technology as a role.

For example:

"Python and AWS experience"
-> skills = ["Python", "AWS"]
-> role = null

==================================================
SKILL POSSESSION
==================================================

These phrases normally indicate skill possession:

worked with
experience with
experienced with
used
knowledge of
familiar with
hands-on experience with
proficient in
experience using
skilled in
expert in

However, they are structured ONLY when their object is a specific known skill.

Example:

"worked with Python"
-> skills = ["Python"]
-> semantic_requirement = null

But:

"worked with Microsoft ecosystem"
-> skills = []
-> semantic_requirement = "worked with Microsoft ecosystem"

==================================================
ACTIONS AND PROJECTS
==================================================

If the recruiter asks what the candidate actually did, use semantic_requirement.

Action examples:

built
developed
created
implemented
designed
deployed
integrated
engineered
trained
optimized
maintained
automated
architected
delivered
migrated
scaled
led
managed
configured
orchestrated
debugged
modernized

Examples:

"developers who built RAG systems"
-> skills = []
-> semantic_requirement = "built RAG systems"

"developers who developed machine learning projects"
-> skills = []
-> semantic_requirement = "developed machine learning projects"

"developers who implemented payment systems"
-> skills = []
-> semantic_requirement = "implemented payment systems"

"developers who designed scalable systems"
-> skills = []
-> semantic_requirement = "designed scalable systems"

==================================================
SKILL + ACTION
==================================================

If there is both a specific skill and a meaningful action/project requirement,
separate them.

"Python developers who built RAG systems"

-> skills = ["Python"]
-> semantic_requirement = "built RAG systems"

"Java developers who developed payment systems"

-> skills = ["Java"]
-> semantic_requirement = "developed payment systems"

"AWS developers who designed scalable systems"

-> skills = ["AWS"]
-> semantic_requirement = "designed scalable systems"

==================================================
IMPORTANT: ACTIONS MUST NOT BECOME SKILLS
==================================================

"built machine learning models"

Do NOT output:

skills = ["machine learning"]

Instead:

skills = []
semantic_requirement = "built machine learning models"

The fact that a known technology appears inside a project description does not
automatically make it a structured skill.

==================================================
ECOSYSTEM RULE
==================================================

The following are broad concepts and should normally be semantic:

ecosystem
technology ecosystem
technology family
technology stack
tech stack
stack
platform family
platforms
products
technology domain
technologies
technology environment
enterprise environment
enterprise stack
cloud ecosystem
AI ecosystem
data ecosystem
Microsoft ecosystem
AWS ecosystem
Java ecosystem

Examples:

"Microsoft ecosystem"
-> semantic

"AWS ecosystem"
-> semantic

"cloud ecosystem"
-> semantic

"enterprise technology stack"
-> semantic

Do not expand these into individual database skills.

==================================================
EXPERIENCE
==================================================

Extract explicit minimum experience.

Examples:

"5 years experience"
-> experience_min_years = 5

"5+ years experience"
-> experience_min_years = 5

"at least 5 years experience"
-> experience_min_years = 5

"minimum 5 years experience"
-> experience_min_years = 5

"8 years experienced candidates"
-> experience_min_years = 8

"candidates with 8 years of experience"
-> experience_min_years = 8

"2.5 years of experience"
-> experience_min_years = 2.5

Do not invent experience requirements.

==================================================
EXPERIENCE SCOPE
==================================================

experience_scope describes what the experience requirement refers to.

Use "SKILL" when the experience requirement is specifically tied to
a particular skill.

Example:

"developers with 5 years of Python experience"

-> experience_min_years = 5
-> experience_scope = "SKILL"
-> skills = ["Python"]

Use "OVERALL" when the experience requirement refers to the candidate's
overall professional experience.

Example:

"developers with 5 years of experience who know Python"

-> experience_min_years = 5
-> experience_scope = "OVERALL"
-> skills = ["Python"]

Use "UNKNOWN" only when an experience requirement is present but the query
does not provide enough information to determine whether the experience is
overall or skill-specific.

If there is no experience requirement:

-> experience_min_years = null
-> experience_scope = null

==================================================
RECENCY
==================================================

Use recency_months only when explicitly stated or clearly implied.

The IMPORTANT rule is:

recency_scope identifies WHAT the recency requirement applies to.

Use:

- "SKILL" when recency applies to a specific structured skill.
- "SEMANTIC" when recency applies to a semantic action, project, or work
  requirement.
- "OVERALL" when recency refers to the candidate's overall professional
  activity.
- "UNKNOWN" only when recency is present but its target cannot safely be
  determined.

Examples:

"recent Python experience"

-> skills = ["Python"]
-> recency_months = 12
-> recency_scope = "SKILL"

"recently used Python"

-> skills = ["Python"]
-> recency_months = 12
-> recency_scope = "SKILL"

"Python experience in the last 6 months"

-> skills = ["Python"]
-> recency_months = 6
-> recency_scope = "SKILL"

"recently worked on machine learning projects"

-> skills = []
-> semantic_requirement = "worked on machine learning projects"
-> recency_months = 12
-> recency_scope = "SEMANTIC"

"Python developers who recently worked on machine learning projects"

-> skills = ["Python"]
-> semantic_requirement = "worked on machine learning projects"
-> recency_months = 12
-> recency_scope = "SEMANTIC"

"Python developers with recent experience"

If the query does not clearly identify what the recent experience refers to:

-> skills = ["Python"]
-> recency_months = 12
-> recency_scope = "UNKNOWN"

"Python developers"

-> recency_months = null
-> recency_scope = null

Do NOT automatically attach recency to a structured skill when the wording
clearly makes recency modify a semantic action or project.

For example:

"Python developers who recently built ML systems"

The recency applies to:

"built ML systems"

NOT automatically to:

"Python"

==================================================
COUNT
==================================================

Extract a count only when explicitly requested.

"find 10 candidates"
-> requested_count = 10
-> count_explicit = true

"find 20 Python developers"
-> requested_count = 20
-> count_explicit = true

"top 5 candidates"
-> requested_count = 5
-> count_explicit = true

"find Python developers"
-> requested_count = null
-> count_explicit = false

Never invent a count.

==================================================
MULTIPLE SPECIFIC SKILLS
==================================================

If multiple specific skills are explicitly required:

"Python and AWS developers"
-> skills = ["Python", "AWS"]

"developers with Python, Docker and PostgreSQL"
-> skills = ["Python", "Docker", "PostgreSQL"]

Do not add related skills.

==================================================
OR REQUIREMENTS
==================================================

The current structured schema cannot represent OR semantics.

Therefore:

"Python or Java developers"

must NOT become:

skills = ["Python", "Java"]

Instead preserve it semantically:

skills = []
semantic_requirement = "Python or Java developers"

This prevents the system from incorrectly treating OR as AND.

==================================================
NEGATION
==================================================

The current structured schema cannot represent exclusions.

For:

"Python developers who do not use Java"

use:

skills = ["Python"]
semantic_requirement = "Python developers who do not use Java"

Do NOT put Java into structured skills.

==================================================
PREFERRED / OPTIONAL
==================================================

The current structured schema cannot represent optional or preferred skills.

For:

"Python developers, preferably with AWS"

use:

skills = ["Python"]
semantic_requirement = "AWS preferred"

Do not make AWS mandatory.

==================================================
AMBIGUOUS TERMS
==================================================

Do not guess the meaning of broad terms.

Examples:

"Microsoft developers"
"cloud developers"
"enterprise developers"
"AI developers"
"data developers"

If the term cannot safely map to one specific database skill, preserve it
semantically.

Do not expand it into multiple skills.

==================================================
HYBRID
==================================================

Hybrid means there is at least one structured requirement AND one semantic
requirement.

Example:

"find 8 years experienced candidates who worked with Microsoft ecosystem"

structured:

skills = []
experience_min_years = 8
experience_scope = "OVERALL"

semantic:

"worked with Microsoft ecosystem"

The resulting route will be HYBRID.

Example:

"find 5 Python developers who built RAG systems"

structured:

skills = ["Python"]

semantic:

"built RAG systems"

The resulting route will be HYBRID.

Example:

"find 10 Python developers who recently worked on machine learning projects"

structured:

skills = ["Python"]
recency_months = 12
recency_scope = "SEMANTIC"

semantic:

"worked on machine learning projects"

The resulting route will be HYBRID.

==================================================
STRUCTURED EXAMPLES
==================================================

"Python developers"

skills = ["Python"]
semantic_requirement = null

"Python developers with 5 years experience"

skills = ["Python"]
experience_min_years = 5
experience_scope = "OVERALL"
semantic_requirement = null

"developers with 5 years of Python experience"

skills = ["Python"]
experience_min_years = 5
experience_scope = "SKILL"
semantic_requirement = null

"backend developers with 5 years of experience"

role = "backend developer"
experience_min_years = 5
experience_scope = "OVERALL"

==================================================
SEMANTIC EXAMPLES
==================================================

"developers who built RAG systems"

skills = []
semantic_requirement = "built RAG systems"

"developers who built payment systems"

skills = []
semantic_requirement = "built payment systems"

"developers who worked with Microsoft ecosystem"

skills = []
semantic_requirement = "worked with Microsoft ecosystem"

==================================================
HYBRID EXAMPLES
==================================================

"Python developers who built RAG systems"

skills = ["Python"]
semantic_requirement = "built RAG systems"

"Python developers who built payment systems"

skills = ["Python"]
semantic_requirement = "built payment systems"

"8 years experienced candidates who worked with Microsoft ecosystem"

skills = []
experience_min_years = 8
experience_scope = "OVERALL"
semantic_requirement = "worked with Microsoft ecosystem"

"Python developers with 5 years experience who built RAG systems"

skills = ["Python"]
experience_min_years = 5
experience_scope = "OVERALL"
semantic_requirement = "built RAG systems"

"Python developers who recently worked on machine learning projects"

skills = ["Python"]
semantic_requirement = "worked on machine learning projects"
recency_months = 12
recency_scope = "SEMANTIC"

==================================================
DATABASE SKILLS
==================================================

{skills_text}

==================================================
RECRUITER QUERY
==================================================

{query}

==================================================
FINAL RULES
==================================================

1. Only extract explicitly requested specific skills.
2. Never invent skills.
3. Never expand ecosystems into technologies.
4. Never expand domains into technologies.
5. Never convert projects into skills.
6. Never convert actions into skills.
7. Keep meaningful project/action requirements semantic.
8. "worked with Python" is structured.
9. "worked with Microsoft ecosystem" is semantic.
10. Role is structured when an explicit candidate role or job title is given.
11. Experience is structured.
12. Use experience_scope to distinguish overall experience from skill-specific experience.
13. Explicit recency is structured.
14. Use recency_scope to identify what the recency requirement applies to.
15. Recency of a semantic action/project must remain attached to the semantic requirement.
16. Explicit count is structured metadata.
17. OR requirements are semantic because the current schema cannot represent OR.
18. Exclusions are semantic because the current schema cannot represent NOT.
19. Preferred skills are semantic because the current schema cannot represent optional requirements.
20. Do not retrieve candidates.
21. Do not rank candidates.
22. Do not evaluate candidates.
23. Do not decide candidate matches.
"""


    llm = _create_llm()

    structured_llm = llm.with_structured_output(
        SearchIntent,
        method="json_schema",
    )

    result = structured_llm.invoke(prompt)

    result.structured_requirements.skills = (
        _normalize_skills(
            result.structured_requirements.skills,
            known_skills,
        )
    )

    requested_count, count_explicit = (
        _normalize_count(
            result.requested_count,
            result.count_explicit,
        )
    )

    result.requested_count = requested_count
    result.count_explicit = count_explicit

    result.requirements = _normalize_requirements(
        result.requirements,
        known_skills,
    )

    # Rebuild the legacy representation from the requirement list so the
    # model cannot leave the two representations inconsistent.
    (
        result.structured_requirements,
        result.semantic_requirement,
    ) = _build_legacy_projection(
        result.requirements,
    )

    result.semantic_requirement = (
        _repair_semantic_requirement(
            result.semantic_requirement,
            result.structured_requirements.skills,
        )
    )

    result.route = _derive_route(
        result.structured_requirements,
        result.semantic_requirement,
        result.requirements,
    )

    return result