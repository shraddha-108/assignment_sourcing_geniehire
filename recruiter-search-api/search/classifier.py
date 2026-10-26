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
        "DOMAIN",
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
    # For EXPERIENCE scope=DOMAIN, value is the numeric minimum and target
    # stores the semantic domain whose employment duration must be measured.
    target: str | None = None
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
        "EXPERIENCE",
        "DOMAIN",
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

class QueryNormalization(BaseModel):
    """Context-preserving normalization of clear spelling/typing errors."""
    normalized_query: str
    changed: bool = False

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

def _normalize_query_for_interpretation(query: str) -> str:
    """Correct clear spelling/typing errors without changing search intent.

    This is deliberately model-driven instead of a hand-maintained typo map.
    It may fix ordinary misspellings, repeated/missing/transposed letters, or
    other obvious typing errors when the intended word is unambiguous from
    context. Technical terms, product names, acronyms, numbers, operators,
    negation, and requirement relationships must be preserved.
    """
    query = str(query or "").strip()
    if not query:
        return query

    prompt = f"""
You are a conservative spelling and typing normalizer for a recruiter search query.

Return the same query with ONLY clear spelling or typing mistakes corrected.
Do not paraphrase, summarize, expand, simplify, or change the recruiter's intent.

Preserve technical skills and technologies, product/platform names, company names,
acronyms, proper nouns, numbers, units, comparison operators, negation, exclusions,
role titles, industries, domains, activities, and the relationships between all
requirements.

A correction is allowed when a misspelled ordinary word is unambiguous from context,
including repeated, missing, or transposed letters. If a token could legitimately be
a technical term, name, acronym, or domain-specific word, leave it unchanged unless
the correction is unambiguous. Do not invent terminology.

RECRUITER QUERY:
{query}
"""
    try:
        normalizer = _create_llm().with_structured_output(
            QueryNormalization,
            method="json_schema",
        )
        result = normalizer.invoke(prompt)
        normalized = str(result.normalized_query or "").strip()
        if normalized:
            return normalized
    except Exception:
        pass
    return query

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
    normalized = " ".join(semantic_requirement.lower().split())
    has_skill = any(
        skill.strip().lower() in normalized
        for skill in skills
        if skill and skill.strip()
    )
    # "experience in/with/using X" is not merely a skill-possession
    # statement. It asks downstream qualification to find evidence that X was
    # actually used. Preserve that semantic evidence requirement even though
    # the requirement also has a structured SKILL component.
    experience_evidence = (
        has_skill
        and "experience" in normalized
        and any(
            marker in normalized
            for marker in (
                "experience in ",
                "experience with ",
                "experience using ",
                "hands-on experience ",
                "professional experience ",
            )
        )
    )
    if not experience_evidence and _is_generic_semantic_phrase(
        semantic_requirement
    ):
        return None
    if not experience_evidence and _is_simple_skill_possession(
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

def _normalize_activity_scope(
    requirement: SearchRequirement,
) -> None:
    """

Normalize the evidence source implied by an activity requirement.

PROJECT and EXPERIENCE are source constraints, not descriptions of the

action itself. They must therefore be inferred only when the recruiter

explicitly identifies the source context.

Examples:

"built machine learning projects"

-> PROJECT

"hands-on experience deploying applications using Docker"

-> EXPERIENCE

"built REST APIs"

-> UNKNOWN

The last case is important: an activity without an explicit source

context may legitimately appear in either a project or professional

experience section.

"""
    if requirement.type != "ACTIVITY":
        return
    text = " ".join(
        str(
            requirement.evidence_query
            or requirement.value
            or ""
        ).lower().split()
    )
    project_pattern = re.compile(
        r"\bproject(?:s|[- ]based)?\b"
    )
    experience_pattern = re.compile(
        r"\b(?:hands[- ]on|professional|work|job|career)\s+experience\b"

r"|\bexperience\s+(?:in|with|using|deploying|on|for)\b"

r"|\bexperience\b"
    )
    if project_pattern.search(text):
        requirement.scope = "PROJECT"
        return
    if experience_pattern.search(text):
        requirement.scope = "EXPERIENCE"
        return
    # Do not trust an LLM-generated PROJECT/EXPERIENCE scope when the query
    # itself does not state that source context. UNKNOWN keeps retrieval broad
    # and lets the evidence validator decide whether the actual evidence is
    # sufficient.
    requirement.scope = "UNKNOWN"
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
}

def _normalize_temporal_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())

def _extract_number_and_unit(query: str) -> tuple[float, str] | None:
    text = _normalize_temporal_text(query)
    patterns = [
        re.compile(
            r"\b(?P<number>\d+(?:\.\d+)?)\s\+?\s*"

r"(?P<unit>years?|yrs?|months?|mos?|weeks?|days?)\b"
        ),
        re.compile(
            r"\b(?P<number>"
            + "|".join(_NUMBER_WORDS)
            + r")\s\+?\s*"

r"(?P<unit>years?|yrs?|months?|mos?|weeks?|days?)\b"
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group("number")
        value = (
            float(raw)
            if raw.replace(".", "", 1).isdigit()
            else float(_NUMBER_WORDS[raw])
        )
        return value, match.group("unit")
    return None

def _duration_to_months(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith(("year", "yr")):
        return value * 12
    if unit.startswith(("month", "mo")):
        return value
    if unit.startswith("week"):
        return value / 4.345
    return value / 30.4375

def _duration_to_years(value: float, unit: str) -> float:
    return _duration_to_months(value, unit) / 12

def _query_skills_near_duration(query: str, known_skills: list[str]) -> list[str]:
    text = _normalize_temporal_text(query)
    duration = _extract_number_and_unit(text)
    if not duration:
        return []
    duration_pattern = re.compile(
        r"\b(?:\d+(?:\.\d+)?|"
        + "|".join(_NUMBER_WORDS)
        + r")\s\+?\s*"

r"(?:years?|yrs?|months?|mos?|weeks?|days?)\b"
    )
    match = duration_pattern.search(text)
    if not match:
        return []
    start = max(0, match.start() - 100)
    end = min(len(text), match.end() + 120)
    window = text[start:end]
    found: list[tuple[int, str]] = []
    for skill in known_skills:
        canonical = skill.strip()
        if not canonical:
            continue
        skill_match = re.search(rf"(?<!\w){re.escape(canonical.lower())}(?!\w)", window)
        if skill_match:
            found.append((abs(skill_match.start() - (match.end() - start)), canonical))
    found.sort(key=lambda item: item[0])
    return [skill for _, skill in found]

def _has_recency_language(query: str) -> bool:
    return bool(re.search(
        r"\b(?:last|past|previous|prior|within|recent|recently|latest|currently|current|since)\b",
        _normalize_temporal_text(query),
    ))

def _has_experience_language(query: str) -> bool:
    return bool(re.search(
        r"\b(?:experience|experienced|working|worked|using|used|hands[- ]on|professional|employment|career)\b",
        _normalize_temporal_text(query),
    ))

def _normalize_experience_scope(
    requirements: list[SearchRequirement],
    known_skills: list[str],
) -> None:
    """Normalize EXPERIENCE scope without using candidate data as taxonomy.

\\`\\`known_skills\\`\\` is a candidate-data vocabulary used for canonical spelling.

It is not a semantic taxonomy: a value appearing in CandidateSkill does not

automatically mean that the recruiter meant a structured SKILL requirement.

Scope precedence:

\\* Explicit DOMAIN is preserved.

\\* Explicit SKILL is canonicalized when possible; an unknown SKILL target

is demoted to DOMAIN rather than becoming a false structured filter.

\\* UNKNOWN/None is resolved from the canonical skill vocabulary only when

there is an exact match. Otherwise a named target becomes DOMAIN.

\\* An EXPERIENCE requirement with no target remains OVERALL.

The function never upgrades DOMAIN -> SKILL merely because the target

happens to occur in candidate skill records.

"""
    known_map = {
        skill.strip().lower(): skill.strip()
        for skill in known_skills
        if skill and skill.strip()
    }
    for requirement in requirements:
        if requirement.type != "EXPERIENCE":
            continue
        target = str(requirement.target or "").strip()
        scope = str(requirement.scope or "").upper()
        if not target:
            if scope in {"SKILL", "UNKNOWN", ""}:
                requirement.scope = "OVERALL"
            continue
        # Preserve the query interpreter's explicit semantic DOMAIN decision.
        # A platform/suite/domain may also exist in candidate skill rows, but
        # that does not make it a structured skill in the recruiter taxonomy.
        if scope == "DOMAIN":
            continue
        canonical_skill = known_map.get(target.lower())
        if scope == "SKILL":
            if canonical_skill:
                requirement.target = canonical_skill
                requirement.scope = "SKILL"
            else:
                # An unrecognized structured skill is unsafe to send through
                # structured filtering. Keep it as semantic domain evidence.
                requirement.scope = "DOMAIN"
            continue
        if canonical_skill:
            requirement.target = canonical_skill
            requirement.scope = "SKILL"
        else:
            requirement.scope = "DOMAIN"

def _normalize_temporal_requirements(
    requirements: list[SearchRequirement],
    query: str,
    known_skills: list[str],
) -> None:
    """Normalize explicit duration-vs-recency semantics independent of wording."""
    duration = _extract_number_and_unit(query)
    if not duration:
        return
    value, unit = duration
    text = _normalize_temporal_text(query)
    target_skills = _query_skills_near_duration(text, known_skills)
    # Explicit recency words win over the generic word 'experience'.
    if _has_recency_language(text):
        months = max(1, int(round(_duration_to_months(value, unit))))
        if _has_action_language(text):
            activities = [r for r in requirements if r.type == "ACTIVITY"]
            if activities:
                activities[0].recency_months = months
                return
        if target_skills:
            targets = {skill.lower() for skill in target_skills}
            for requirement in requirements:
                if requirement.type == "SKILL" and requirement.value.lower() in targets:
                    requirement.recency_months = months
                    return
        for requirement in requirements:
            if requirement.recency_months is not None:
                requirement.recency_months = months
                return
        return
    if not _has_experience_language(text):
        return
    years = _duration_to_years(value, unit)
    value_text = str(years).rstrip("0").rstrip(".")
    experience_requirements = [
        requirement
        for requirement in requirements
        if requirement.type == "EXPERIENCE"
    ]
    domain_requirements = [
        requirement
        for requirement in experience_requirements
        if requirement.scope == "DOMAIN"
    ]
    skill_requirements = [
        requirement
        for requirement in experience_requirements
        if requirement.scope == "SKILL"
    ]
    # If the interpreter explicitly identified a DOMAIN requirement, do not
    # let lexical matching against known_skills manufacture a SKILL requirement.
    # This keeps the candidate-data vocabulary separate from the recruiter
    # semantic taxonomy.
    if domain_requirements:
        for requirement in domain_requirements:
            requirement.value = value_text
            requirement.operator = "GTE"
            requirement.recency_months = None
        # If the same query also contains explicit structured skill experience,
        # normalize those existing requirements without creating new ones from
        # every known skill mentioned near the duration.
        for index, requirement in enumerate(skill_requirements):
            requirement.value = value_text
            requirement.operator = "GTE"
            requirement.scope = "SKILL"
            if target_skills:
                requirement.target = target_skills[
                    min(index, len(target_skills) - 1)
                ]
            requirement.recency_months = None
        target_set = {skill.lower() for skill in target_skills}
        for requirement in requirements:
            if (
                requirement.type == "SKILL"
                and requirement.value.lower() in target_set
            ):
                requirement.recency_months = None
        return
    # No explicit DOMAIN requirement exists. Exact known skills mentioned near
    # the duration can therefore be used as a fallback for skill-specific
    # EXPERIENCE when the interpreter did not emit one itself.
    if target_skills:
        if not skill_requirements:
            for skill in target_skills:
                requirements.append(
                    SearchRequirement(
                        type="EXPERIENCE",
                        value=value_text,
                        target=skill,
                        required=True,
                        operator="GTE",
                        scope="SKILL",
                    )
                )
        else:
            for index, requirement in enumerate(skill_requirements):
                requirement.value = value_text
                requirement.operator = "GTE"
                requirement.scope = "SKILL"
                requirement.target = target_skills[
                    min(index, len(target_skills) - 1)
                ]
                requirement.recency_months = None
            existing_targets = {
                str(requirement.target or "").strip().lower()
                for requirement in skill_requirements
            }
            for skill in target_skills:
                if skill.lower() not in existing_targets:
                    requirements.append(
                        SearchRequirement(
                            type="EXPERIENCE",
                            value=value_text,
                            target=skill,
                            required=True,
                            operator="GTE",
                            scope="SKILL",
                        )
                    )
        target_set = {skill.lower() for skill in target_skills}
        for requirement in requirements:
            if (
                requirement.type == "SKILL"
                and requirement.value.lower() in target_set
            ):
                requirement.recency_months = None
        return
    # No target was identified near the duration and no DOMAIN requirement
    # exists, so the duration represents overall professional experience.
    experience_requirements = [r for r in requirements if r.type == "EXPERIENCE"]
    if not experience_requirements:
        experience_requirements = [
            SearchRequirement(
                type="EXPERIENCE",
                value=value_text,
                required=True,
                operator="GTE",
                scope="OVERALL",
            )
        ]
        requirements.extend(experience_requirements)
    for requirement in experience_requirements:
        if requirement.scope in {None, "UNKNOWN", "OVERALL"}:
            requirement.value = value_text
            requirement.operator = "GTE"
            requirement.scope = "OVERALL"
            requirement.target = None
            requirement.recency_months = None

def _remove_unstated_experience_requirements(
    requirements: list[SearchRequirement],
    query: str,
    known_skills: list[str],
) -> list[SearchRequirement]:
    """Remove LLM-inferred experience when the query does not express it.

A duration attached to a skill (for example, "2 years of Python") is

ambiguous without an explicit experience/work/usage relation. The

deterministic temporal normalizer already avoids creating such an

experience requirement; this guard also removes an EXPERIENCE item if the

LLM created one anyway.

Standalone durations without a nearby canonical skill are left untouched

so existing overall-experience behavior remains compatible.

"""
    if _has_experience_language(query):
        return requirements
    duration = _extract_number_and_unit(query)
    if not duration:
        return requirements
    target_skills = _query_skills_near_duration(
        query,
        known_skills,
    )
    if not target_skills:
        return requirements
    return [
        requirement
        for requirement in requirements
        if requirement.type != "EXPERIENCE"
    ]

def _query_has_duration(query: str) -> bool:
    """Return True when the recruiter explicitly supplied a duration."""
    return _extract_number_and_unit(query) is not None

def _skill_from_requirement_target(
    requirement: SearchRequirement,
    known_skills: list[str],
) -> str | None:
    """Resolve a requirement target/value to one explicitly named known skill."""
    known_map = {
        skill.strip().lower(): skill.strip()
        for skill in known_skills
        if skill and skill.strip()
    }
    candidates = [
        str(requirement.target or "").strip(),
        str(requirement.value or "").strip(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        canonical = known_map.get(candidate.lower())
        if canonical:
            return canonical
    return None

def _normalize_undated_experience_requirements(
    requirements: list[SearchRequirement],
    query: str,
    known_skills: list[str],
) -> None:
    """Normalize experience wording that has no explicit duration.

Undated experience expresses demonstrated use, not a numeric minimum.

The semantic scope chosen by the query interpreter is preserved:

    - EXPERIENCE + SKILL may be canonicalized into a structured SKILL

      requirement with semantic experience evidence.

    - EXPERIENCE + DOMAIN remains semantic DOMAIN experience.

    - UNKNOWN/unspecified named experience remains semantic rather than being

      promoted to a structured skill merely because the target appears in

      candidate-derived known_skills.

``known_skills`` is therefore used only for canonical spelling, never as

    the authority for deciding SKILL versus DOMAIN.

    """
    if _query_has_duration(query):
        return
    for requirement in requirements:
        if requirement.type != "EXPERIENCE":
            continue
        target = str(requirement.target or "").strip()
        value = str(requirement.value or "").strip()
        evidence = str(requirement.evidence_query or "").strip()
        scope = str(requirement.scope or "").upper()
        # DOMAIN is already a semantic decision. Do not convert it to SKILL
        # just because the same platform/domain happens to occur in candidate
        # skill records.
        if scope == "DOMAIN":
            semantic_target = target or value
            semantic_text = evidence or (
                f"experience with {semantic_target}"
                if semantic_target
                else "professional work experience"
            )
            requirement.type = "OTHER"
            requirement.value = semantic_text
            requirement.target = semantic_target or None
            requirement.required = True
            requirement.operator = "CONTAINS"
            requirement.scope = "EXPERIENCE"
            requirement.evidence_query = semantic_text
            continue
        # Only an explicitly classified SKILL experience may become a
        # structured skill. Here known_skills is only a canonicalization
        # dictionary, not a semantic taxonomy.
        if scope == "SKILL":
            skill = _skill_from_requirement_target(
                requirement,
                known_skills,
            )
            if skill:
                requirement.type = "SKILL"
                requirement.value = skill
                requirement.target = None
                requirement.required = True
                requirement.operator = "EQ"
                requirement.scope = "EXPERIENCE"
                requirement.evidence_query = (
                    evidence or f"experience using {skill}"
                )
                continue
            # An uncanonicalized SKILL target is unsafe as a structured
            # filter. Preserve it as semantic evidence instead.
            semantic_target = target or value
            semantic_text = evidence or (
                f"experience with {semantic_target}"
                if semantic_target
                else "professional work experience"
            )
            requirement.type = "OTHER"
            requirement.value = semantic_text
            requirement.target = semantic_target or None
            requirement.required = True
            requirement.operator = "CONTAINS"
            requirement.scope = "EXPERIENCE"
            requirement.evidence_query = semantic_text
            continue
        # UNKNOWN/unspecified experience with a named target remains semantic.
        # Do not infer SKILL solely from candidate-derived vocabulary.
        semantic_target = target or value
        semantic_text = evidence or (
            f"experience with {semantic_target}"
            if semantic_target
            else "professional work experience"
        )
        requirement.type = "OTHER"
        requirement.value = semantic_text
        requirement.target = semantic_target or None
        requirement.required = True
        requirement.operator = "CONTAINS"
        requirement.scope = "EXPERIENCE"
        requirement.evidence_query = semantic_text

def _normalize_requirements(
    requirements: list[SearchRequirement],
    known_skills: list[str],
    query: str,
) -> list[SearchRequirement]:
    """

Canonicalize requirements without inventing skills or evidence scope.

Unknown skills remain semantic rather than becoming false structured

filters. Activity evidence scope is normalized from explicit wording so

project evidence is not incorrectly required for generic activities.

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
        _normalize_activity_scope(
            requirement
        )
        normalized.append(requirement)
    # Preserve the interpreter's semantic SKILL/DOMAIN decision.
    # known_skills is used only for canonicalization, never as a taxonomy.
    _normalize_experience_scope(
        normalized,
        known_skills=known_skills,
    )
    _normalize_undated_experience_requirements(
        normalized,
        query=query,
        known_skills=known_skills,
    )
    _normalize_temporal_requirements(
        normalized,
        query=query,
        known_skills=known_skills,
    )
    # Temporal normalization can add or rewrite EXPERIENCE requirements.
    _normalize_experience_scope(
        normalized,
        known_skills=known_skills,
    )
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
            if requirement.scope == "EXPERIENCE":
                semantic_parts.append(
                    requirement.evidence_query
                    or f"experience using {requirement.value}"
                )
            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "SKILL"
        elif requirement.type == "ROLE":
            role = requirement.value
            if requirement.recency_months is not None:
                recency_months = requirement.recency_months
                recency_scope = "OVERALL"
        elif requirement.type == "EXPERIENCE":
            if requirement.scope == "SKILL":
                # Only canonical SKILL experience contributes a structured
                # skill filter. DOMAIN experience remains semantic.
                target = str(requirement.target or "").strip()
                if target and target not in skills:
                    skills.append(target)
                try:
                    experience_min_years = float(requirement.value)
                except (TypeError, ValueError):
                    experience_min_years = None
                experience_scope = "SKILL"
                if requirement.recency_months is not None:
                    recency_months = requirement.recency_months
                    recency_scope = "SKILL"
            elif requirement.scope == "OVERALL":
                try:
                    experience_min_years = float(requirement.value)
                except (TypeError, ValueError):
                    experience_min_years = None
                experience_scope = requirement.scope
                if requirement.recency_months is not None:
                    recency_months = requirement.recency_months
                    recency_scope = "OVERALL"
            elif requirement.scope == "DOMAIN":
                # Domain experience is validated from employment evidence and
                # its date ranges. Do not turn it into overall experience.
                semantic_parts.append(
                    requirement.evidence_query
                    or requirement.value
                )
                if requirement.recency_months is not None:
                    recency_months = requirement.recency_months
                    recency_scope = "SEMANTIC"
            else:
                experience_scope = "UNKNOWN"
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

class RequirementRecovery(BaseModel):
    """Focused recovery schema used when the primary parser omits a requirement."""
    requirements: list[SearchRequirement] = Field(default_factory=list)

def _has_explicit_experience_relation(query: str) -> bool:
    """Return True when the query explicitly describes an experience/work relation."""
    text = _normalize_temporal_text(query)
    patterns = (
        r"\b(?:\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\s+"
        r"(?:years?|yrs?|months?|mos?|weeks?|days?)\s+of\s+"
        r"experience\s+(?:with|in|using|on|across|within)\b",
        r"\b(?:hands[- ]on\s+)?experience\s+(?:with|in|using|on|across|within)\b",
        r"\b(?:experienced|working|worked)\s+(?:with|in|using|on|across|within)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)

def _extract_experience_target_fallback(query: str) -> tuple[str, str] | None:
    """Extract one direct experience target for the final deterministic fallback.

    This is deliberately conservative. It only handles a direct experience
    relationship such as ``experience with X``. Complex multi-requirement
    queries should be handled by the focused LLM recovery step above.
    """
    text = _normalize_temporal_text(query)
    patterns = (
        r"\b(?:\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\s+"
        r"(?:years?|yrs?|months?|mos?|weeks?|days?)\s+of\s+"
        r"experience\s+(?:with|in|using|on|across|within)\s+(?P<target>.+)$",
        r"\b(?:hands[- ]on\s+)?experience\s+(?:with|in|using|on|across|within)\s+(?P<target>.+)$",
        r"\b(?:experienced|working|worked)\s+(?:with|in|using|on|across|within)\s+(?P<target>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        target = match.group("target").strip(" .,:;!?\"")
        target = re.split(
            r"\s+(?:but|who|that|which|where|while|plus|along with)\s+",
            target,
            maxsplit=1,
        )[0].strip(" .,:;!?\"")
        if not target or target in {"it", "this", "that", "something"}:
            continue
        return target, match.group(0).strip()
    return None

def _recover_missing_experience_requirements(
    query: str,
) -> list[SearchRequirement]:
    """Recover explicit experience requirements omitted by the primary parser.

    The primary query interpreter remains the source of truth when it emits a
    requirement. This recovery path is only activated when the query clearly
    expresses an experience relationship but no EXPERIENCE requirement was
    produced. A focused LLM pass preserves the semantic distinction between a
    discrete skill and a broader domain. If that pass also fails, the final
    deterministic fallback keeps the requirement semantic DOMAIN rather than
    manufacturing a structured skill from candidate-derived vocabulary.
    """
    if not _has_explicit_experience_relation(query):
        return []
    recovery_prompt = f"""
You are a recovery parser for a recruiter candidate-search system.

The primary query parser failed to emit an explicit experience requirement.
Extract ONLY the recruiter's explicit EXPERIENCE requirements from the query.
Do not retrieve or evaluate candidates.

Rules:
- Return one EXPERIENCE requirement for each independently stated experience
  relationship.
- Use operator GTE only when a numeric duration is explicitly stated.
- For a specific discrete technology/skill such as Python, Java, React, or
  Docker, use scope SKILL and put the technology in target.
- For a named platform, suite, ecosystem, broad technology area, business
  technology, system family, or other semantic domain, use scope DOMAIN and
  put that named domain in target. Do not turn it into a list of skills.
- Never use the candidate database or a supplied skill list as a taxonomy.
- For undated experience, preserve demonstrated experience without inventing
  a duration. Use value=\"experience\" and operator CONTAINS.
- Preserve the recruiter's wording in evidence_query.
- If the query contains no explicit experience relationship, return an empty
  requirements list.

RECRUITER QUERY:
{query}
"""
    try:
        recovery_llm = _create_llm().with_structured_output(
            RequirementRecovery,
            method="json_schema",
        )
        recovered = recovery_llm.invoke(recovery_prompt)
        requirements = [
            requirement
            for requirement in recovered.requirements
            if requirement.type == "EXPERIENCE"
            and str(requirement.target or "").strip()
        ]
        if requirements:
            return requirements
    except Exception:
        # The deterministic fallback below still prevents an explicit
        # experience query from silently becoming an empty search.
        pass
    fallback = _extract_experience_target_fallback(query)
    if not fallback:
        return []
    target, evidence = fallback
    duration = _extract_number_and_unit(query)
    if duration:
        value, unit = duration
        value_text = str(_duration_to_years(value, unit)).rstrip("0").rstrip(".")
        return [
            SearchRequirement(
                type="EXPERIENCE",
                value=value_text,
                target=target,
                required=True,
                operator="GTE",
                scope="DOMAIN",
                evidence_query=evidence,
            )
        ]
    return [
        SearchRequirement(
            type="EXPERIENCE",
            value="experience",
            target=target,
            required=True,
            operator="CONTAINS",
            scope="DOMAIN",
            evidence_query=evidence,
        )
    ]

def _find_relevant_skill_candidates(
    query: str,
    known_skills: list[str],
    max_candidates: int = 50,
) -> list[str]:
    """Find canonical skills explicitly mentioned in the recruiter query.

This is only a high-recall lexical gate for prompt-size control. It does

not classify requirements or expand broad domains into technology lists.

The complete known_skills collection is still used after the LLM response

for deterministic canonicalization.

"""
    text = query.strip().lower()
    if not text:
        return []
    matches: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for skill in known_skills:
        canonical = skill.strip()
        if not canonical:
            continue
        key = canonical.lower()
        if key in seen:
            continue
        if _contains_phrase(text, key):
            matches.append((len(key), text.find(key), canonical))
            seen.add(key)
    matches.sort(key=lambda item: (-item[0], item[1], item[2].lower()))
    return [skill for _, _, skill in matches[:max_candidates]]

def classify_search_intent(
    query: str,
    known_skills: list[str],
) -> SearchIntent:
    query = query.strip()
    interpretation_query = _normalize_query_for_interpretation(query)
    relevant_skill_candidates = _find_relevant_skill_candidates(
        query=interpretation_query,
        known_skills=known_skills,
    )
    skills_text = "\n".join(
        f"- {skill}"
        for skill in relevant_skill_candidates
    )
    if not skills_text:
        skills_text = "(none explicitly matched; do not invent a canonical skill)"
    prompt = f"""

You are the query-understanding layer for a recruiter candidate search system.

Your ONLY job is to convert the recruiter's natural-language request into the structured SearchIntent schema. Do not retrieve, rank, qualify, or evaluate candidates.

Extract:

1. requested_count and whether the count was explicit

2. requirements: the source of truth, with one independently verifiable recruiter requirement per item

3. reason: a short explanation of the interpretation

Core rules:

\- Extract only what the recruiter explicitly asks for. Never invent candidate facts or unstated technologies.

\- Minor spelling or typing mistakes must not change the interpreted intent. Interpret the corrected meaning when an ordinary word is clearly misspelled, but do not guess when a term is ambiguous.

\- SKILL means one discrete structured technical competency explicitly requested, such as Python, Java, React, Docker, or PostgreSQL. ROLE means an explicit job title/role. Do not turn a broad domain, platform family, product suite, ecosystem, business application, or technology area into a list of skills.

\- DOMAIN is used for experience with a named platform, suite, ecosystem, system family, broad technology area, business technology, or other semantic domain when it is not being requested as a discrete structured skill. Examples include an ERP platform, CRM suite, enterprise application family, backend technologies, payment systems, or a fintech domain.

\- The supplied KNOWN SKILL CANDIDATES are only lexical canonicalization hints. They are NOT a taxonomy and their presence must never decide SKILL versus DOMAIN. Candidate data may contain platform names, product suites, or domain concepts in CandidateSkill fields; do not promote those values into structured skills merely because they appear in the list.

\- When the recruiter asks for a numeric duration with a named target, first determine the semantic kind of the target. Use SKILL only when the target is a discrete structured technical competency. Use DOMAIN when the target is a platform, suite, ecosystem, system family, broad technology area, business application, or other domain concept.

\- ACTIVITY captures work/actions such as built REST APIs, deployed applications, implemented authentication, or developed ML systems. Use PROJECT scope only when project work is explicit; use EXPERIENCE scope for hands-on/professional/work/employment experience; otherwise use UNKNOWN.

\- INDUSTRY captures explicit industry/domain experience requirements.

\- EXPERIENCE uses operator GTE only when a numeric duration is explicitly present. Scope is SKILL for a discrete structured skill, OVERALL for total professional experience, DOMAIN for a platform/domain/system-area experience requirement, and UNKNOWN only when the scope cannot be determined.

\- "experience in Python", "experience with Python", and "Python experience" mean demonstrated Python work/use, but they do NOT imply any minimum number of years. Represent the explicit Python skill and preserve an evidence_query describing experience using Python. Never invent "1 year" or another duration.

\- "5 years of Python experience" means EXPERIENCE value=5, operator=GTE, scope=SKILL, target=Python, plus the Python skill requirement when appropriate.

\- "5 years of experience who know Python" means overall professional experience plus a Python skill requirement.

\- "5 years of experience with backend technologies" means EXPERIENCE value=5, operator=GTE, scope=DOMAIN, target/value describing backend technologies. Keep the domain semantic; do not expand it into a hard-coded skill list.

\- "5 years of experience with an ERP platform" means EXPERIENCE value=5, operator=GTE, scope=DOMAIN. The named platform is semantic domain experience, not automatically a structured skill.

\- "5 years of experience with a CRM suite" means EXPERIENCE value=5, operator=GTE, scope=DOMAIN. The named suite is semantic domain experience, not automatically a structured skill.

\- A duration does NOT by itself establish an EXPERIENCE requirement. Only create EXPERIENCE when the recruiter explicitly expresses experience, work, usage, employment, or a comparable duration relationship. A bare duration attached to a skill, such as "2 years of Python", must remain a SKILL requirement unless the query explicitly establishes that the duration measures experience.

\- Explicit recency language takes precedence over duration semantics. Examples of recency language include last, past, previous, within, recently, latest, current/currently, or since.

\- Attach recency_months to the requirement it actually modifies. Do not attach recency to a skill merely because that skill appears elsewhere in the query.

\- "Python used in the last 6 months" is skill recency; "recently built ML projects" is activity/project recency; "5 years of experience" is experience duration, not recency.

\- Preserve the recruiter's wording in evidence_query for semantic requirements so downstream retrieval can find evidence.

\- Role is structured only when the recruiter explicitly requests a role/title. Do not convert generic technology/domain language into a job title.

\- Multiple requirements are normally independent AND requirements unless the recruiter explicitly expresses OR, NOT, or preference. Use operator PREFERRED for explicitly preferred/optional requirements and NOT for explicit exclusions.

\- Do not decide whether any candidate satisfies a requirement. Do not produce candidate IDs or matches.

Examples:

"Python developers" -> SKILL Python

"finance managers with 6 years experience in IT industry" -> ROLE finance manager; EXPERIENCE 6 GTE OVERALL; INDUSTRY IT with semantic evidence

"Python developers who recently built machine learning projects" -> SKILL Python; ACTIVITY built machine learning projects, scope PROJECT, recency 12 months

"developers with 5 years of Python experience" -> EXPERIENCE 5 GTE SKILL target Python; SKILL Python

"developers with 2 years of Python" -> SKILL Python only; do not infer an EXPERIENCE requirement

"developers with experience in Python" -> SKILL Python with EXPERIENCE evidence; no numeric minimum

"developers with experience using Java" -> SKILL Java with EXPERIENCE evidence; no numeric minimum

"developers with 5 years of experience with backend technologies" -> EXPERIENCE 5 GTE DOMAIN target backend technologies with semantic evidence

"built REST APIs" -> ACTIVITY built REST APIs, scope UNKNOWN

"hands-on experience deploying applications using Docker" -> ACTIVITY deploying applications using Docker, scope EXPERIENCE

The final route and legacy structured fields are rebuilt deterministically by Python after your response. For EXPERIENCE scope, your SKILL/DOMAIN decision is semantic information: do not change DOMAIN to SKILL just because a matching phrase appears in KNOWN SKILL CANDIDATES. Return only the structured SearchIntent object required by the schema.

KNOWN SKILL CANDIDATES MENTIONED IN QUERY:

{skills_text}

RECRUITER QUERY:

{interpretation_query}

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
    result.requirements = _remove_unstated_experience_requirements(
        result.requirements,
        query=interpretation_query,
        known_skills=known_skills,
    )
    # The requirement list is the source of truth. If the primary LLM omitted
    # an explicit experience relationship, recover it before normalization so
    # the search layer never interprets a meaningful request as an empty
    # structured search.
    if (
        _has_explicit_experience_relation(interpretation_query)
        and not any(
            requirement.type == "EXPERIENCE"
            for requirement in result.requirements
        )
    ):
        result.requirements.extend(
            _recover_missing_experience_requirements(interpretation_query)
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
        interpretation_query,
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
