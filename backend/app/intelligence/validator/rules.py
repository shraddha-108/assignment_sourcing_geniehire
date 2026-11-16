import re
import os
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.experience import Experience
from app.database.models.resume_section import ResumeSection
from app.search.normalization import (
    company_name_matches,
    equivalent_terms,
    role_matches as _role_matches,
)

def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return set(re.findall(r"[a-z0-9+#.]+", value.lower()))


_SEMANTIC_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from",
    "has", "have", "in", "into", "is", "of", "on", "or", "the",
    "their", "to", "who", "with",
}

_BUILD_ACTIONS = {
    "build", "builds", "building", "built",
    "develop", "develops", "developing", "developed",
    "create", "creates", "creating", "created",
    "designs", "designing", "designed",
    "launch", "launches", "launching", "launched",
    "implement", "implements", "implementing", "implemented",
    "ship", "ships", "shipping", "shipped",
    "engineered",
    "prototype", "prototypes", "prototyping", "prototyped",
    "construct", "constructs", "constructing", "constructed",
    "architecting", "architected",
}

_INTEGRATION_ACTIONS = {
    "integrate", "integrates", "integrating", "integrated",
}

_AI_TERMS = {
    "ai", "ml", "llm", "llms", "genai", "chatgpt", "chatbot", "chatbots",
    "rag", "copilot", "machine", "learning", "artificial", "intelligence",
}

_ML_FRAMEWORK_TERMS = {
    "scikit", "sklearn", "tensorflow", "pytorch", "keras", "xgboost",
    "lightgbm", "catboost",
}

_ML_METHOD_TERMS = {
    "classification", "classifier", "clustering", "supervised",
    "unsupervised", "neural", "nlp",
}

_PROJECT_CONTEXT_TERMS = {
    "project", "projects", "prototype", "application", "app",
    "system", "model", "models", "classifier", "pipeline",
}

_ML_IMPLEMENTATION_TERMS = _ML_FRAMEWORK_TERMS | _ML_METHOD_TERMS | {
    "model", "models", "training", "trained", "dataset", "datasets",
    "algorithm", "algorithms", "preprocessing", "prediction",
    "predictive", "features", "feature",
}

_ML_WORK_ACTIONS = _BUILD_ACTIONS | {
    "work", "worked", "working", "train", "trained", "training",
    "use", "used", "using", "applied", "apply", "deployed",
}

_PRODUCT_TERMS = {
    "product", "products", "platform", "platforms", "application",
    "applications", "app", "apps", "software", "system", "systems",
    "tool", "tools", "solution", "solutions", "service", "services",
    "feature", "features", "model", "models", "chatbot", "chatbots",
    "workflow", "workflows", "assistant", "assistants",
}

_BUILT_PRODUCT_TERMS = _PRODUCT_TERMS - {
    "tool", "tools", "model", "models",
}

SEMANTIC_SUPPORT_MIN_RERANKER_SCORE = float(
    os.getenv("SEMANTIC_SUPPORT_MIN_RERANKER_SCORE", "0.0")
)

_CUSTOMER_RELATIONSHIP_SIGNALS = re.compile(
    r"\b(?:CRM|customer relationship management|client relationship management|"
    r"account management|relationship manager|account manager|customer success|"
    r"customer engagement|customer retention|client relationships?|salesforce|hubspot|"
    r"dynamics\s*(?:365\s*)?(?:CRM|customer engagement)|"
    r"d365\s*(?:CRM|customer engagement)|zoho\s*CRM)\b",
    re.IGNORECASE,
)

_CUSTOMER_RELATIONSHIP_ADJACENT_SIGNALS = re.compile(
    r"\b(?:d365|dynamics\s*365|dynamics\s*ax|finance\s*(?:&|and)\s*operations)\b",
    re.IGNORECASE,
)

_CUSTOMER_RELATIONSHIP_WORK_ACTIONS = re.compile(
    r"\b(?:administered|analyzed|automated|built|configured|consulted|coordinated|"
    r"created|customized|delivered|deployed|designed|developed|engaged|executed|"
    r"facilitated|handled|implemented|integrated|led|leveraged|maintained|managed|"
    r"migrated|monitored|operated|oversaw|owned|processed|provided|supported|"
    r"strengthened|streamlined|tracked|trained|used|utilized|worked)\b",
    re.IGNORECASE,
)

_CUSTOMER_RELATIONSHIP_ROLE_TITLES = re.compile(
    r"\b(?:customer success|account|relationship|crm)\s+"
    r"(?:manager|administrator|analyst|consultant|developer|engineer|"
    r"executive|lead|representative|specialist)\b",
    re.IGNORECASE,
)

_DISTRIBUTED_SYSTEM_SIGNALS = re.compile(
    r"\b(distribut(?:ed|ion)|microservices?|service[- ]oriented|"
    r"event[- ]driven|message queues?|message brokers?|pub/?sub|kafka|"
    r"rabbitmq|grpc|multi[- ]node|cluster(?:ing)?|sharding|partitioning|"
    r"replication|fault[- ]tolerant|service[- ]to[- ]service)\b",
    re.IGNORECASE,
)

_SCALABILITY_SIGNALS = re.compile(
    r"\b(horizontal(?:ly)? scal(?:e|ing)|scale[- ]out|load balanc(?:er|ing)|"
    r"high availability|high throughput|elastic(?:ity| scaling)|auto[- ]scal(?:e|ing)|"
    r"traffic spikes?|concurrent users?|performance at scale|millions? of users|"
    r"handle (?:a )?\w+ (?:requests|users|transactions) per second|"
    r"reduced? (?:latency|response time) by \d+%|increased? throughput by \d+%)\b",
    re.IGNORECASE,
)

_ROLE_LEVEL_PREFIXES = {
    "junior", "jr", "senior", "sr", "lead", "principal",
    "staff", "associate", "assistant", "chief", "head",
}
_ROLE_LEVEL_SUFFIXES = {"i", "ii", "iii", "iv", "v", "1", "2", "3", "4", "5"}

_NEGATIVE_TECH_WORK_ACTIONS = _BUILD_ACTIONS | {
    "work", "worked", "working", "use", "used", "using",
    "apply", "applied", "deploy", "deployed", "maintain", "maintained",
    "develop", "developed", "implement", "implemented", "write", "wrote",
    "program", "programmed", "code", "coded", "test", "tested",
    "debug", "debugged", "integrate", "integrated", "automate", "automated",
    "manage", "managed", "build", "built",
}

_NEGATIVE_TECH_PROFESSIONAL_CONTEXT = {
    "developer", "developers", "engineer", "engineers", "programmer",
    "programmers", "software", "backend", "frontend", "fullstack",
    "full-stack", "application", "applications", "system", "systems",
    "service", "services", "api", "apis", "project", "projects",
    "platform", "platforms", "production", "professional",
}


def _semantic_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|[\n;]+", text)
        if sentence.strip()
    ]


def _experience_duration_months(experience: Experience) -> int | None:
    if not experience.start_date:
        return None
    end_date = date.today() if experience.is_current else experience.end_date
    if not end_date:
        return None
    months = (end_date.year - experience.start_date.year) * 12
    months += end_date.month - experience.start_date.month
    if end_date.day < experience.start_date.day:
        months -= 1
    return max(0, months)


def _normalize_role_for_match(value: str | None) -> str:
    ordered = re.findall(r"[a-z0-9+#.]+", (value or "").casefold())
    while ordered and ordered[0] in _ROLE_LEVEL_PREFIXES:
        ordered.pop(0)
    while ordered and ordered[-1] in _ROLE_LEVEL_SUFFIXES:
        ordered.pop()
    return " ".join(ordered)


def _combined_experience_months(experiences: list[Experience]) -> int:
    intervals = []
    for experience in experiences:
        if not experience.start_date:
            continue
        end_date = date.today() if experience.is_current else experience.end_date
        if end_date and end_date >= experience.start_date:
            intervals.append((experience.start_date, end_date))
    if not intervals:
        return 0

    intervals.sort(key=lambda interval: interval[0])
    merged = []
    for start_date, end_date in intervals:
        if merged and start_date <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_date))
        else:
            merged.append((start_date, end_date))

    total_months = 0
    for start_date, end_date in merged:
        months = (end_date.year - start_date.year) * 12
        months += end_date.month - start_date.month
        if end_date.day < start_date.day:
            months -= 1
        total_months += max(0, months)
    return total_months


def _experience_source_label(experience: Experience) -> str:
    role = experience.role.title if experience.role else "Experience"
    company = experience.company.name if experience.company else None
    start = experience.start_date.strftime("%b %Y") if experience.start_date else "Date not listed"
    end_date = date.today() if experience.is_current else experience.end_date
    end = "Present" if experience.is_current else (
        end_date.strftime("%b %Y") if end_date else "Date not listed"
    )
    position = f"{role} at {company}" if company else role
    return f"{position} ({start} - {end})"


def _matched_experience_payload(experience: Experience) -> dict:
    return {
        "experience_id": experience.id,
        "role": experience.role.title if experience.role else None,
        "company": experience.company.name if experience.company else None,
        "start_date": experience.start_date.isoformat() if experience.start_date else None,
        "end_date": experience.end_date.isoformat() if experience.end_date else None,
        "is_current": bool(experience.is_current),
        "duration_months": _experience_duration_months(experience),
    }


def _select_best_matching_experience(
    requested_role: str,
    experiences: list[Experience],
) -> Experience | None:
    requested_normalized = _normalize_role_for_match(requested_role)
    if not requested_normalized:
        return None

    alias_normalized = {
        _normalize_role_for_match(alias)
        for alias in equivalent_terms(requested_role, "role")
    }

    candidates = []
    for experience in experiences:
        if not experience.role or not experience.role.title:
            continue
        actual_normalized = _normalize_role_for_match(experience.role.title)
        if not actual_normalized:
            continue

        if actual_normalized == requested_normalized:
            match_strength = 2
        elif actual_normalized in alias_normalized:
            match_strength = 1
        elif _role_matches(requested_role, experience.role.title):
            match_strength = 1
        else:
            continue

        start_date = experience.start_date or date.min
        candidates.append((
            match_strength,
            1 if experience.is_current else 0,
            start_date,
            experience.id or 0,
            experience,
        ))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (item[0], item[1], item[2], item[3]),
        reverse=True,
    )
    return candidates[0][-1]


def _company_matches(
    requested_company: str,
    actual_company: str | None,
    equivalents: list[str] | None = None,
) -> bool:
    return company_name_matches(actual_company, equivalents or [requested_company])


def _matching_evidence(
    evidence: list[dict],
    query: str,
    preferred_types: set[str] | None = None,
) -> list[dict]:
    terms = _tokens(query)
    candidates = []
    for item in evidence:
        text = str(item.get("text") or "")
        text_terms = _tokens(text)
        overlap = len(terms & text_terms) / max(1, len(terms))
        if overlap <= 0:
            continue
        source_type = str(item.get("evidence_type") or "").lower()
        source_bonus = 0.1 if preferred_types and source_type in preferred_types else 0.0
        candidates.append((overlap + source_bonus, item))
    if not candidates:
        return []
    return [max(candidates, key=lambda pair: pair[0])[1]]


def _format_months(months: int) -> str:
    years, remaining_months = divmod(max(0, months), 12)
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if remaining_months:
        parts.append(f"{remaining_months} month{'s' if remaining_months != 1 else ''}")
    return " ".join(parts) or "0 months"


def _experience_requirement_label(
    minimum: float | None,
    maximum: float | None,
) -> str:
    if minimum is not None and maximum is not None:
        return f"{minimum:g}–{maximum:g} years experience"
    if minimum is not None:
        return f"at least {minimum:g} years experience"
    return f"up to {maximum:g} years experience"


def _technology_terms(requirement: str) -> set[str]:
    return {
        token
        for token in _tokens(requirement)
        if token not in _SEMANTIC_STOP_WORDS
        and token not in {"not", "without", "exclude", "excluding", "avoid"}
    }


def _supports_negative_technology_evidence(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
) -> str | None:
    technology_terms = _technology_terms(requirement)
    if not technology_terms:
        return None

    source_type = (evidence_type or "").casefold()
    if source_type in {"skill", "skills", "education"}:
        return None

    for sentence in _semantic_sentences(evidence_text):
        tokens = _tokens(sentence)
        if not technology_terms.intersection(tokens):
            continue

        has_work_action = bool(tokens & _NEGATIVE_TECH_WORK_ACTIONS)
        has_professional_context = bool(tokens & _NEGATIVE_TECH_PROFESSIONAL_CONTEXT)

        if source_type in {"project", "experience"}:
            if has_work_action or has_professional_context:
                return sentence
            continue

        if source_type == "summary":
            if has_work_action or (
                has_professional_context
                and len(technology_terms.intersection(tokens)) > 0
            ):
                return sentence
            continue

        if has_work_action and has_professional_context:
            return sentence

    return None


def _candidate_has_structured_skill(
    db: Session,
    candidate_id: int,
    requirement: str,
) -> bool:
    candidate_skill_rows = db.scalars(
        select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
    ).all()

    aliases = equivalent_terms(requirement, "skill") or [requirement]
    alias_keys = {_normalize(alias) for alias in aliases}

    for row in candidate_skill_rows:
        if not row.skill:
            continue
        skill_name = _normalize(row.skill.normalized_name)
        if skill_name in alias_keys:
            return True

    return False


def _normalize_for_source(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _resolve_experience_source(db: Session, candidate_id: int, evidence: dict):
    if evidence.get("source_kind") == "experience_record":
        experience = db.get(Experience, evidence.get("experience_id"))
        return experience if experience and experience.candidate_id == candidate_id else None
    section_id = evidence.get("resume_section_id")
    source_id = evidence.get("source_id") or evidence.get("evidence_id")
    if section_id is None and source_id is not None:
        from app.database.models.candidate_evidence import CandidateEvidence
        row = db.get(CandidateEvidence, source_id)
        section_id = row.resume_section_id if row else None
    section = db.get(ResumeSection, section_id) if section_id is not None else None
    if section is None or section.section_type.casefold() != "experience":
        return None
    section_text = _normalize_for_source(section.content)
    if not section_text:
        return None
    experiences = db.scalars(
        select(Experience).where(Experience.candidate_id == candidate_id)
    ).all()
    resolved = []
    for experience in experiences:
        description = _normalize_for_source(experience.description)
        if description and (description in section_text or section_text in description):
            resolved.append(experience)
    if len(resolved) == 1:
        return resolved[0]
    if len(resolved) > 1:
        return None

    stop_words = _SEMANTIC_STOP_WORDS | {
        "work", "worked", "working", "experience", "project", "projects",
        "develop", "developed", "build", "built", "create", "created",
        "design", "designed", "implement", "implemented",
    }
    passage_tokens = _tokens(evidence.get("text")) - stop_words
    if len(passage_tokens) < 2:
        return None
    scored = []
    for experience in experiences:
        description_tokens = _tokens(experience.description) - stop_words
        if len(description_tokens) < 2:
            continue
        overlap = len(passage_tokens & description_tokens)
        coverage = overlap / min(len(passage_tokens), len(description_tokens))
        if overlap >= 2 and coverage >= 0.65:
            scored.append((coverage, overlap, experience))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][:2] == scored[1][:2]:
        return None
    return scored[0][2]
