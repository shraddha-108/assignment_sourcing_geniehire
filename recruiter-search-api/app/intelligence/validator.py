import re
import math
import os
from time import perf_counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.experience import Experience
from app.database.models.resume_section import ResumeSection
from app.database.location_utils import format_candidate_location, location_matches
from app.search.normalization import (
    equivalent_terms,
    industry_evidence_matches,
    industry_evidence_terms,
)


def _normalize(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        value.lower().strip().split()
    )


def _tokens(value: str | None) -> set[str]:

    if not value:
        return set()

    return set(
        re.findall(
            r"[a-z0-9+#.]+",
            value.lower(),
        )
    )


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

# CrossEncoder output is an additional semantic evidence signal for valid
# paraphrases that do not share enough literal tokens with the query.
SEMANTIC_SUPPORT_MIN_RERANKER_SCORE = float(
    os.getenv("SEMANTIC_SUPPORT_MIN_RERANKER_SCORE", "0.0")
)


def _semantic_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|[\n;]+", text)
        if sentence.strip()
    ]


def _has_ai_concept(tokens: set[str]) -> bool:
    return bool(tokens & _AI_TERMS) or {
        "artificial", "intelligence"
    }.issubset(tokens) or {"machine", "learning"}.issubset(tokens)


def _is_ai_build_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_to_build = bool(tokens & _BUILD_ACTIONS)
    asks_about_ai = _has_ai_concept(tokens)
    return asks_to_build and asks_about_ai


def _is_ecommerce_build_requirement(requirement: str) -> bool:
    text = requirement.casefold().replace("e-commerce", "ecommerce")
    tokens = _tokens(text)
    asks_to_build = bool(tokens & _BUILD_ACTIONS)
    asks_about_ecommerce = bool(
        "ecommerce" in tokens
        or {"online", "store"}.issubset(tokens)
        or {"shopping", "cart"}.issubset(tokens)
    )
    return asks_to_build and asks_about_ecommerce


def _supports_ecommerce_build(sentence: str) -> bool:
    text = sentence.casefold().replace("e-commerce", "ecommerce")
    tokens = _tokens(text)
    ecommerce_context = bool(
        "ecommerce" in tokens
        or {"online", "store"}.issubset(tokens)
        or {"shopping", "cart"}.issubset(tokens)
        or {"online", "sales"}.issubset(tokens)
        or {"online", "ordering"}.issubset(tokens)
        or {"retail", "platform"}.issubset(tokens)
    )
    return ecommerce_context and bool(tokens & _BUILD_ACTIONS)


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


def _is_distributed_system_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_about_system_design = bool(
        tokens & {"system", "systems", "architecture", "platform", "platforms"}
    )
    asks_about_distributed_scale = bool(
        tokens & {"distributed", "scalable", "scalability"}
    )
    return asks_about_system_design and asks_about_distributed_scale


def _supports_distributed_system_design(sentence: str) -> bool:
    tokens = _tokens(sentence)
    has_design_action = bool(tokens & _BUILD_ACTIONS)
    has_distributed_evidence = bool(_DISTRIBUTED_SYSTEM_SIGNALS.search(sentence))
    has_scalability_evidence = bool(_SCALABILITY_SIGNALS.search(sentence))
    return (
        has_design_action
        and has_distributed_evidence
        and has_scalability_evidence
    )


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


def _is_ml_project_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_about_ml = (
        {"machine", "learning"}.issubset(tokens)
        or "ml" in tokens
        or {"deep", "learning"}.issubset(tokens)
    )
    asks_about_projects = bool(tokens & {"project", "projects"})
    return asks_about_ml and asks_about_projects


def _supports_ml_project(
    sentence: str,
    evidence_type: str | None,
) -> bool:
    tokens = _tokens(sentence)
    has_ml_signal = (
        {"machine", "learning"}.issubset(tokens)
        or "ml" in tokens
        or {"deep", "learning"}.issubset(tokens)
        or bool(tokens & _ML_FRAMEWORK_TERMS)
        or bool(tokens & _ML_METHOD_TERMS)
        or {"computer", "vision"}.issubset(tokens)
    )
    if not has_ml_signal:
        return False

    is_computer_vision = {"computer", "vision"}.issubset(tokens)
    has_implementation_detail = (
        bool(tokens & _ML_IMPLEMENTATION_TERMS)
        or is_computer_vision
    )
    # A project heading such as "ML-Based Fake News Detection System" is
    # explicit enough on its own; broad mentions of an ML department or role
    # are not.
    explicit_ml_based_project = (
        "ml" in tokens
        and "based" in tokens
        and bool(tokens & _PROJECT_CONTEXT_TERMS)
        and (evidence_type or "").lower() == "project"
    )
    if not has_implementation_detail and not explicit_ml_based_project:
        return False

    # A project title or an ML skills list alone does not establish that
    # the candidate worked on an ML project. Require an action in the same
    # sentence as the ML evidence.
    has_work_action = bool(tokens & _ML_WORK_ACTIONS)
    if not has_work_action and not explicit_ml_based_project:
        return False

    # Project evidence directly supplies project context. Other sections
    # must explicitly connect the work to a project, model, or application.
    if (evidence_type or "").lower() == "project":
        return True

    has_project_context = bool(tokens & _PROJECT_CONTEXT_TERMS)
    return has_project_context and has_work_action


def _supports_ai_build(sentence: str) -> bool:
    words = re.findall(r"[a-z0-9+#.]+", sentence.lower())
    action_positions = [
        index
        for index, word in enumerate(words)
        if word in _BUILD_ACTIONS
    ]
    integration_positions = [
        index
        for index, word in enumerate(words)
        if word in _INTEGRATION_ACTIONS
    ]
    product_positions = [
        index
        for index, word in enumerate(words)
        if word in _PRODUCT_TERMS
    ]
    ai_positions = [
        index
        for index, word in enumerate(words)
        if word in _AI_TERMS
    ]

    built_product_positions = [
        index
        for index, word in enumerate(words)
        if word in _BUILT_PRODUCT_TERMS
    ]

    # Require the build action, product, and AI mention to be close together.
    # This reduces false matches where someone built something unrelated but
    # mentions using AI tools elsewhere in the same resume sentence.
    direct_build_pairs = [
        (action, product, ai)
        for action in action_positions
        for product in product_positions
        for ai in ai_positions
        if abs(action - product) <= 8
        and abs(ai - product) <= 6
        and abs(action - ai) <= 8
    ]

    # "Integrated AI tools" alone may describe using existing tools. Count
    # integration only when the passage ties AI to a product feature/system.
    integration_pairs = [
        (action, product, ai)
        for action in integration_positions
        for product in built_product_positions
        for ai in ai_positions
        if abs(action - product) <= 6
        and abs(ai - product) <= 4
        and abs(action - ai) <= 6
    ]

    pairs = direct_build_pairs or integration_pairs
    if not pairs:
        return False

    return True


def _semantic_support_score(
    requirement: str,
    sentence: str,
    evidence_type: str | None,
) -> float:
    if industry_evidence_terms(requirement):
        base_score = 0.85 if industry_evidence_matches(sentence, requirement) else 0.0
    elif _is_distributed_system_requirement(requirement):
        base_score = 0.9
    elif _is_ecommerce_build_requirement(requirement):
        base_score = 0.85
    elif re.search(r"\bback[- ]end\s+(?:tech|technolog(?:y|ies|ical))\b", requirement, re.IGNORECASE):
        base_score = 0.85
    elif _is_ml_project_requirement(requirement):
        tokens = _tokens(sentence)
        base_score = (
            1.0
            if {"machine", "learning"}.issubset(tokens)
            else 0.9
        )
    elif _is_ai_build_requirement(requirement):
        words = re.findall(r"[a-z0-9+#.]+", sentence.lower())
        action_positions = [
            index for index, word in enumerate(words)
            if word in _BUILD_ACTIONS
        ]
        product_positions = [
            index for index, word in enumerate(words)
            if word in _PRODUCT_TERMS
        ]
        ai_positions = [
            index for index, word in enumerate(words)
            if word in _AI_TERMS
        ]
        distances = [
            abs(action - product)
            + abs(ai - product)
            + abs(action - ai)
            for action in action_positions
            for product in product_positions
            for ai in ai_positions
            if abs(action - product) <= 8
            and abs(ai - product) <= 6
            and abs(action - ai) <= 8
        ]

        if not distances:
            integration_positions = [
                index for index, word in enumerate(words)
                if word in _INTEGRATION_ACTIONS
            ]
            built_product_positions = [
                index for index, word in enumerate(words)
                if word in _BUILT_PRODUCT_TERMS
            ]
            distances = [
                abs(action - product)
                + abs(ai - product)
                + abs(action - ai)
                for action in integration_positions
                for product in built_product_positions
                for ai in ai_positions
                if abs(action - product) <= 6
                and abs(ai - product) <= 4
                and abs(action - ai) <= 6
            ]

        base_score = (
            0.7 + 0.3 * (1.0 - min(min(distances), 24) / 24.0)
            if distances
            else 0.0
        )
    else:
        content_tokens = {
            token
            for token in _tokens(requirement)
            if token not in _SEMANTIC_STOP_WORDS
        }
        sentence_tokens = _tokens(sentence)
        base_score = (
            len(content_tokens & sentence_tokens) / len(content_tokens)
            if content_tokens
            else 0.0
        )

    source_weight = {
        "project": 1.0,
        "experience": 0.98,
        "summary": 0.85,
        "skill": 0.80,
    }.get((evidence_type or "").lower(), 0.90)
    return base_score * source_weight


def _supports_semantic_requirement(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
    reranker_score: float | None = None,
) -> str | None:
    """Return the sentence supporting a requirement, or None if unsupported."""

    requirement_tokens = _tokens(requirement)
    content_tokens = {
        token
        for token in requirement_tokens
        if token not in _SEMANTIC_STOP_WORDS
    }
    specialized_requirement = (
        _is_ml_project_requirement(requirement)
        or _is_ai_build_requirement(requirement)
        or _has_ai_concept(requirement_tokens)
        or _is_ecommerce_build_requirement(requirement)
        or _is_distributed_system_requirement(requirement)
        or _is_microsoft_ecosystem_requirement(requirement)
        or _is_cloud_technology_requirement(requirement)
        or bool(industry_evidence_terms(requirement))
    )

    if industry_evidence_terms(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if industry_evidence_matches(sentence, requirement):
                return sentence

    if _is_microsoft_ecosystem_requirement(requirement):
        microsoft_signals = re.compile(
            r"(?<!\w)\.net\b|\bc\s*#\b|\b(?:d365|dynamics\s*365|dynamics\s+(?:crm|customer engagement)|"
            r"business central|power\s*(?:apps|automate|bi|platform|pages)|azure|"
            r"microsoft\s*(?:365|365|office\s*365)|sharepoint|teams|sql\s*server|"
            r"entra\s*id|azure\s*active\s*directory)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if microsoft_signals.search(sentence):
                return sentence

    if _is_cloud_technology_requirement(requirement):
        cloud_signals = re.compile(
            r"\b(?:aws|amazon\s+web\s+services|azure|microsoft\s+azure|"
            r"gcp|google\s+cloud(?:\s+platform)?|oracle\s+cloud|ibm\s+cloud|"
            r"cloud\s+(?:computing|infrastructure|platform|services?)|"
            r"kubernetes|serverless|iaas|paas|cloud\s+storage)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if cloud_signals.search(sentence):
                return sentence

    if re.search(r"\bback[- ]end\s+(?:tech|technolog(?:y|ies|ical))\b", requirement, re.IGNORECASE):
        backend_signals = re.compile(
            r"\b(backend|back-end|server[- ]side|rest(?:ful)?|graphql|api|apis|"
            r"database|sql|postgres(?:ql)?|mysql|mongodb|redis|microservices?|"
            r"fastapi|django|flask|spring|express(?:\.js)?|node\.js|asp\.net)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if backend_signals.search(sentence):
                return sentence

    if _is_ecommerce_build_requirement(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if _supports_ecommerce_build(sentence):
                return sentence

    if _is_distributed_system_requirement(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if _supports_distributed_system_design(sentence):
                return sentence

    sentences = _semantic_sentences(evidence_text)
    for sentence in sentences:
        sentence_tokens = _tokens(sentence)

        if _is_ml_project_requirement(requirement):
            if _supports_ml_project(sentence, evidence_type):
                return sentence
            continue

        if _is_ai_build_requirement(requirement):
            if _supports_ai_build(sentence):
                return sentence
            continue

        if _is_ecommerce_build_requirement(requirement):
            if _supports_ecommerce_build(sentence):
                return sentence
            continue

        if _is_distributed_system_requirement(requirement):
            if _supports_distributed_system_design(sentence):
                return sentence
            continue

        if not content_tokens:
            continue

        # Require most of the meaningful query terms in the same sentence;
        # a single generic mention such as "AI" is not enough to qualify.
        overlap = len(content_tokens & sentence_tokens)
        required_overlap = max(1, math.ceil(len(content_tokens) * 0.6))

        if overlap >= required_overlap:
            return sentence

    # Literal token overlap misses paraphrases such as "architected a
    # horizontally scaled distributed platform" for a request about
    # designing scalable distributed systems. Require a strong reranker
    # signal over the actual stored passage before accepting such evidence.
    if (
        not specialized_requirement
        and reranker_score is not None
        and float(reranker_score) >= SEMANTIC_SUPPORT_MIN_RERANKER_SCORE
        and sentences
    ):
        return max(
            sentences,
            key=lambda sentence: len(content_tokens & _tokens(sentence)),
        )

    return None


def _is_microsoft_ecosystem_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\bmicrosoft\s+(?:technology|technologies|ecosystem|stack)\b",
        requirement,
        re.IGNORECASE,
    ))


def _is_cloud_technology_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\bcloud\s+(?:technology|technologies|ecosystem|platforms?)\b",
        requirement,
        re.IGNORECASE,
    ))


def _role_matches(
    requested_role: str,
    actual_role: str | None,
) -> bool:

    requested = _tokens(
        requested_role
    )

    actual = _tokens(
        actual_role
    )

    return bool(requested and actual and (
        requested.issubset(actual)
        or any(_tokens(alias).issubset(actual)
            for alias in equivalent_terms(requested_role, "role"))
    ))


def _company_matches(
    requested_company: str,
    actual_company: str | None,
) -> bool:

    return (
        _normalize(
            requested_company
        )
        == _normalize(
            actual_company
        )
    )


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
        parts.append(
            f"{remaining_months} month{'s' if remaining_months != 1 else ''}"
        )
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


def validate_structured_requirements(
    db: Session,
    candidate_id: int,
    requirements: dict,
    evidence: list[dict],
) -> tuple[bool, list[dict], list[dict], list[dict]]:
    """
    Validate hard structured requirements.

    PostgreSQL is the source of truth for:
    - skills, roles, companies, location, total experience
    """

    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id
        )
    )

    if candidate is None:
        return (
            False,
            [
                {
                    "type": "CANDIDATE",
                    "reason": "Candidate not found",
                }
            ],
            [],
            [],
        )

    failures = []
    matched = []
    matched_evidence = []

    def add_match(
        requirement_type: str,
        requirement: str,
        candidate_value,
        supporting: list[dict] | None = None,
    ) -> None:
        supporting = supporting or []
        supporting = [
            {**item, "requirement": requirement}
            for item in supporting
        ]
        matched.append({
            "type": requirement_type,
            "requirement": requirement,
            "matched": True,
            "candidate_value": candidate_value,
            "evidence": supporting,
        })
        matched_evidence.extend(supporting)

    requested_location = requirements.get("location")
    if requested_location:
        if not location_matches(requested_location, candidate.location):
            failures.append({
                "type": "LOCATION",
                "required": requested_location,
                "available": format_candidate_location(candidate.location),
            })
        else:
            add_match(
                "location",
                requested_location,
                format_candidate_location(candidate.location),
            )

    # --------------------------------------------------
    # Skills
    # --------------------------------------------------

    requested_skills = (
        requirements.get("skills")
        or []
    )
    skill_alias_groups = requirements.get("skill_aliases") or {}
    requested_roles = requirements.get("roles") or []
    role_experiences = []
    if requested_roles:
        role_experiences = db.scalars(
            select(Experience).where(
                Experience.candidate_id == candidate_id
            )
        ).all()

    if requested_skills:

        candidate_skill_rows = db.scalars(
            select(CandidateSkill)
            .where(
                CandidateSkill.candidate_id
                == candidate_id
            )
        ).all()

        candidate_skills = {
            _normalize(row.skill.normalized_name): row
            for row in candidate_skill_rows
            if row.skill
        }

        for skill in requested_skills:

            alias_terms = skill_alias_groups.get(skill) or equivalent_terms(skill, "skill") or [skill]
            skill_row = next((candidate_skills.get(_normalize(alias))
                for alias in alias_terms if candidate_skills.get(_normalize(alias))), None)
            if skill_row is None:
                failures.append(
                    {
                        "type": "SKILL",
                        "required": skill,
                    }
                )
            else:
                skill_evidence = []
                if requested_roles:
                    qualifying_experiences = [
                        experience
                        for experience in role_experiences
                        if experience.role
                        and experience.role.title
                        and any(
                            _role_matches(role, experience.role.title)
                            for role in requested_roles
                        )
                        and any(_tokens(alias).issubset(_tokens(experience.description))
                            for alias in alias_terms if _tokens(alias))
                    ]
                    if not qualifying_experiences:
                        failures.append({
                            "type": "SKILL_EVIDENCE",
                            "required": skill,
                            "reason": f"No matching {', '.join(requested_roles)} experience describes using {skill}.",
                        })
                        continue
                    skill_evidence = [{
                        "candidate_id": candidate_id,
                        "evidence_type": "experience",
                        "source_id": experience.id,
                        "source_kind": "experience_record",
                        "experience_id": experience.id,
                        "text": experience.description,
                        "retrieval_score": 0.0,
                    } for experience in qualifying_experiences[:2]]
                if not requested_roles and skill_row.evidence:
                    skill_evidence.append({
                        "candidate_id": candidate_id,
                        "evidence_type": "skill",
                        "source_id": skill_row.id,
                        "text": skill_row.evidence,
                        "retrieval_score": 0.0,
                    })
                if not skill_evidence and not requested_roles:
                    skill_evidence = _matching_evidence(
                        evidence,
                        skill,
                        preferred_types={"skills", "experience", "project"},
                    )
                add_match("skill", skill, skill_row.skill.name, skill_evidence)

    # --------------------------------------------------
    # Total experience
    # --------------------------------------------------

    minimum_years = requirements.get(
        "min_experience_years"
    )

    maximum_years = requirements.get(
        "max_experience_years"
    )

    actual_months = int(
        candidate.total_experience_months
        or 0
    )
    minimum_exclusive = bool(requirements.get("min_experience_exclusive"))

    if minimum_years is not None:

        required_months = (
            float(minimum_years)
            * 12
        )

        if actual_months < required_months or (minimum_exclusive and actual_months <= required_months):

            failures.append(
                {
                    "type": "MIN_EXPERIENCE",
                    "required_years": float(
                        minimum_years
                    ),
                    "actual_months": actual_months,
                }
            )

    if maximum_years is not None:

        maximum_months = (
            float(maximum_years)
            * 12
        )

        if actual_months > maximum_months:

            failures.append(
                {
                    "type": "MAX_EXPERIENCE",
                    "required_years": float(
                        maximum_years
                    ),
                    "actual_months": actual_months,
                }
            )

    minimum_passes = (
        minimum_years is None
        or (actual_months > float(minimum_years) * 12 if minimum_exclusive
            else actual_months >= float(minimum_years) * 12)
    )
    experience_passes = (
        minimum_passes
        and (maximum_years is None or actual_months <= float(maximum_years) * 12)
    )
    if minimum_years is not None or maximum_years is not None:
        if experience_passes:
            add_match(
                "experience",
                _experience_requirement_label(minimum_years, maximum_years),
                _format_months(actual_months),
            )

    # --------------------------------------------------
    # Roles
    # --------------------------------------------------

    requested_roles = (
        requirements.get("roles")
        or []
    )

    if requested_roles:
        for role in requested_roles:
            matched_experience = next(
                (experience for experience in role_experiences
                 if experience.role and experience.role.title
                 and _role_matches(role, experience.role.title)),
                None,
            )
            if not matched_experience:
                failures.append(
                    {
                        "type": "ROLE",
                        "required": role,
                        "available": [
                            experience.role.title for experience in role_experiences
                            if experience.role and experience.role.title
                        ],
                    }
                )
            else:
                role_evidence = ([{
                    "candidate_id": candidate_id,
                    "evidence_type": "experience",
                    "source_id": matched_experience.id,
                    "source_kind": "experience_record",
                    "experience_id": matched_experience.id,
                    "text": matched_experience.description,
                    "retrieval_score": 0.0,
                }] if matched_experience.description else [])
                add_match(
                    "role", role, matched_experience.role.title, role_evidence
                )

    # --------------------------------------------------
    # Companies
    # --------------------------------------------------

    requested_companies = (
        requirements.get("companies")
        or []
    )

    if requested_companies:

        experiences = db.scalars(
            select(Experience)
            .where(
                Experience.candidate_id
                == candidate_id
            )
        ).all()

        for company in requested_companies:
            matched_company = next(
                (
                    experience for experience in experiences
                    if experience.company and experience.company.name
                    and _company_matches(company, experience.company.name)
                ),
                None,
            )
            if not matched_company:
                failures.append(
                    {
                        "type": "COMPANY",
                        "required": company,
                        "available": [
                            experience.company.name for experience in experiences
                            if experience.company and experience.company.name
                        ],
                    }
                )
            else:
                company_evidence = ([{
                    "candidate_id": candidate_id,
                    "evidence_type": "experience",
                    "source_id": matched_company.id,
                    "source_kind": "experience_record",
                    "experience_id": matched_company.id,
                    "text": matched_company.description,
                    "retrieval_score": 0.0,
                }] if matched_company.description else [])
                add_match(
                    "company", company, matched_company.company.name,
                    company_evidence,
                )

    return (
        len(failures) == 0,
        failures,
        matched,
        matched_evidence,
    )


def validate_semantic_requirements(
    candidate_id: int,
    semantic_requirements: list[str],
    evidence: list[dict],
) -> tuple[bool, list[dict], list[dict], list[dict]]:
    """
    Validate semantic requirements using the retrieved
    and CrossEncoder-reranked evidence.

    No LLM is used here.

    The semantic requirement must have supporting evidence.
    """

    if not semantic_requirements:
        return True, [], [], []

    failures = []

    if not evidence:
        failures = [
            {
                "type": "SEMANTIC",
                "reason": "No supporting evidence found",
            }
        ]
        return False, failures, [], [
            {
                "type": "semantic",
                "requirement": requirement,
                "matched": False,
                "evidence": [],
            }
            for requirement in semantic_requirements
        ]

    supporting_evidence = []
    matched_requirements = []
    for requirement in semantic_requirements:
        best_match = None
        best_support_score = 0.0
        for item in evidence:
            if str(item.get("evidence_type") or "").casefold() in {
                "skill", "skills", "education"
            }:
                continue
            text = str(item.get("text") or "")
            matched_sentence = _supports_semantic_requirement(
                requirement=requirement,
                evidence_text=text,
                evidence_type=item.get("evidence_type"),
                reranker_score=item.get("reranker_score"),
            )

            if matched_sentence:
                support_score = _semantic_support_score(
                    requirement=requirement,
                    sentence=matched_sentence,
                    evidence_type=item.get("evidence_type"),
                )

                if support_score <= best_support_score:
                    continue

                if len(matched_sentence) > 600:
                    matched_sentence = (
                        matched_sentence[:597].rsplit(" ", 1)[0]
                        + "..."
                    )

                best_match = {
                    **item,
                    "requirement": requirement,
                    "text": matched_sentence,
                    "semantic_support_score": support_score,
                }
                best_support_score = support_score

        if best_match is not None:
            supporting_evidence.append(best_match)
            matched_requirements.append({
                "type": "semantic",
                "requirement": requirement,
                "matched": True,
                "evidence": [best_match],
            })
        else:
            failures.append(
                {
                    "type": "SEMANTIC",
                    "required": requirement,
                    "reason": "Retrieved passages did not contain clear supporting evidence",
                }
            )
            matched_requirements.append({
                "type": "semantic",
                "requirement": requirement,
                "matched": False,
                "evidence": [],
            })

    return (
        len(failures) == 0,
        failures,
        supporting_evidence,
        matched_requirements,
    )


def validate_candidate(
    db: Session,
    candidate_id: int,
    structured_requirements: dict,
    semantic_requirements: list[str],
    evidence: list[dict],
    requirements_graph: list | None = None,
    candidate_semantic_scores: dict[str, float] | None = None,
    candidate_semantic_min_score: float = 0.0,
    soft_semantic_scores: dict[str, float] | None = None,
    soft_semantic_evidence: dict[str, list[dict]] | None = None,
) -> dict:

    requirements_graph = requirements_graph or []
    semantic_or_groups: dict[str, list] = {}
    structured_or_groups: dict[str, list] = {}
    all_or_groups: dict[str, list] = {}
    for requirement in requirements_graph:
        if requirement.group_id and requirement.relationship.upper() == "OR" and requirement.mandatory:
            all_or_groups.setdefault(requirement.group_id, []).append(requirement)
    mixed_or_groups = {
        group_id: items for group_id, items in all_or_groups.items()
        if any("semantic_evidence_retrieval" in item.capabilities for item in items)
        and any(set(item.capabilities) & {
            "structured_candidate_lookup", "structured_experience_lookup"
        } for item in items)
    }
    mixed_or_ids = {item.id for items in mixed_or_groups.values() for item in items}
    grouped_texts = set()
    for requirement in requirements_graph:
        if "semantic_evidence_retrieval" in requirement.capabilities and requirement.id in mixed_or_ids:
            grouped_texts.add(_normalize(
                str(requirement.value) if isinstance(requirement.value, str)
                else requirement.normalized_text
            ))
        if (
            requirement.group_id
            and requirement.relationship.upper() == "OR"
            and "semantic_evidence_retrieval" in requirement.capabilities
            and requirement.id not in mixed_or_ids
        ):
            semantic_or_groups.setdefault(requirement.group_id, []).append(requirement)
            grouped_texts.add(_normalize(
                str(requirement.value) if isinstance(requirement.value, str)
                else requirement.normalized_text
            ))
        if (
            requirement.group_id
            and requirement.relationship.upper() == "OR"
            and requirement.mandatory
            and requirement.id not in mixed_or_ids
            and set(requirement.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }
        ):
            structured_or_groups.setdefault(requirement.group_id, []).append(requirement)
    independent_semantic_requirements = [
        requirement for requirement in semantic_requirements
        if _normalize(requirement) not in grouped_texts
    ]

    handled_structured_or_groups = {}
    for group_id, alternatives in structured_or_groups.items():
        mapped_alternatives = []
        for alternative in alternatives:
            field = (alternative.field or "").casefold()
            value = alternative.value
            if field in {"skill", "skills"} and isinstance(value, str):
                requirement_filter = {"skills": [value]}
            elif field in {"role", "roles"} and isinstance(value, str):
                requirement_filter = {"roles": [value]}
            elif field in {"company", "companies"} and isinstance(value, str):
                requirement_filter = {"companies": [value]}
            elif field == "location" and isinstance(value, str):
                requirement_filter = {"location": value}
            elif field in {"experience", "total_experience"} and isinstance(value, dict):
                requirement_filter = {
                    "min_experience_years": value.get("min_experience_years"),
                    "max_experience_years": value.get("max_experience_years"),
                }
            elif field in {"min_experience_years", "max_experience_years"} and value is not None:
                requirement_filter = {field: value}
            else:
                requirement_filter = {}
            if requirement_filter:
                mapped_alternatives.append((alternative, requirement_filter))
        if len(mapped_alternatives) == len(alternatives) and len(alternatives) > 1:
            handled_structured_or_groups[group_id] = mapped_alternatives

    effective_structured_requirements = {
        **structured_requirements,
        "skills": list(structured_requirements.get("skills") or []),
        "roles": list(structured_requirements.get("roles") or []),
        "companies": list(structured_requirements.get("companies") or []),
    }
    for mapped_alternatives in handled_structured_or_groups.values():
        for _, requirement_filter in mapped_alternatives:
            for field, value in requirement_filter.items():
                if value is None:
                    continue
                if field in {"skills", "roles", "companies"}:
                    alternative_values = {_normalize(str(item)) for item in value}
                    effective_structured_requirements[field] = [
                        item for item in effective_structured_requirements[field]
                        if _normalize(str(item)) not in alternative_values
                    ]
                elif _normalize(str(effective_structured_requirements.get(field))) == _normalize(str(value)):
                    effective_structured_requirements[field] = None

    # Remove structured members of a mixed structured/semantic OR group from
    # the unconditional hard filter. Each alternative is checked below as part
    # of the shared OR group.
    for alternatives in mixed_or_groups.values():
        for alternative in alternatives:
            if not set(alternative.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }:
                continue
            field = (alternative.field or "").casefold()
            value = alternative.value
            target = {"skill": "skills", "role": "roles", "company": "companies"}.get(field, field)
            if target in {"skills", "roles", "companies"} and value:
                aliases = equivalent_terms(str(value), "skill" if target == "skills" else "role") if target in {"skills", "roles"} else [str(value)]
                alias_keys = {_normalize(alias) for alias in aliases}
                effective_structured_requirements[target] = [
                    item for item in effective_structured_requirements[target]
                    if _normalize(str(item)) not in alias_keys
                ]
            elif target in effective_structured_requirements and value is not None:
                if _normalize(str(effective_structured_requirements.get(target))) == _normalize(str(value)):
                    effective_structured_requirements[target] = None

    qualification_started = perf_counter()
    structured_valid, structured_failures, structured_matches, structured_evidence = (
        validate_structured_requirements(
            db=db,
            candidate_id=candidate_id,
            requirements=effective_structured_requirements,
            evidence=evidence,
        )
    )
    for group_id, mapped_alternatives in handled_structured_or_groups.items():
        alternative_results = []
        for alternative, requirement_filter in mapped_alternatives:
            passed, failures, matches, matched_evidence = validate_structured_requirements(
                db=db,
                candidate_id=candidate_id,
                requirements=requirement_filter,
                evidence=evidence,
            )
            alternative_results.append((alternative, passed, matches, matched_evidence))
        group_matched = any(passed for _, passed, _, _ in alternative_results)
        if not group_matched:
            structured_valid = False
            structured_failures.append({
                "type": "STRUCTURED_OR",
                "group_id": group_id,
                "required": [item.original_text for item, _ in mapped_alternatives],
                "reason": "No alternative in this requirement group matched the candidate profile",
            })
        for alternative, passed, matches, matched_evidence in alternative_results:
            alternative_type = matches[0].get("type") if matches else "structured"
            structured_matches.append({
                **(matches[0] if matches else {
                    "type": alternative_type,
                    "requirement": alternative.original_text,
                    "candidate_value": None,
                    "evidence": [],
                }),
                "requirement_id": alternative.id,
                "group_id": group_id,
                "relationship": "OR",
                "mandatory": True,
                "matched": passed,
            })
            if passed:
                structured_evidence.extend(matched_evidence)
    soft_requirement_matches = []
    for requirement in requirements_graph:
        if requirement.mandatory or not set(requirement.capabilities) & {
            "structured_candidate_lookup", "structured_experience_lookup"
        }:
            continue
        field = (requirement.field or "").casefold()
        value = requirement.value
        soft_filters = {}
        match_type = {
            "skills": "skill", "skill": "skill",
            "roles": "role", "role": "role",
            "companies": "company", "company": "company",
        }.get(field, field)
        if field in {"skill", "skills"} and value:
            soft_filters["skills"] = [str(value)]
        elif field in {"role", "roles"} and value:
            soft_filters["roles"] = [str(value)]
        elif field in {"company", "companies"} and value:
            soft_filters["companies"] = [str(value)]
        elif field == "location" and value:
            soft_filters["location"] = str(value)
        elif field in {"experience", "total_experience"} and isinstance(value, dict):
            soft_filters.update(value)
            soft_filters["min_experience_exclusive"] = requirement.min_experience_exclusive
            match_type = "experience"
        elif field in {"min_experience_years", "max_experience_years"} and value is not None:
            soft_filters[field] = value
            match_type = "experience"
        if not soft_filters:
            continue
        preference_passed, _, preference_matches, _ = validate_structured_requirements(
            db=db,
            candidate_id=candidate_id,
            requirements=soft_filters,
            evidence=evidence,
        )
        if preference_passed and preference_matches:
            for match in preference_matches:
                soft_requirement_matches.append({
                    **match,
                    "requirement_id": requirement.id,
                    "matched": True,
                    "mandatory": False,
                })
        else:
            soft_requirement_matches.append({
                "type": match_type,
                "requirement_id": requirement.id,
                "requirement": requirement.original_text,
                "matched": False,
                "mandatory": False,
                "candidate_value": None,
                "evidence": [],
            })

    qualification_duration = perf_counter() - qualification_started
    evidence_validation_started = perf_counter()
    semantic_valid, semantic_failures, supporting_evidence, semantic_matches = (
        validate_semantic_requirements(
            candidate_id=candidate_id,
            semantic_requirements=independent_semantic_requirements,
            evidence=evidence,
        )
    )
    matched_requirements = structured_matches + semantic_matches
    matched_requirements.extend(soft_requirement_matches)

    for group_id, alternatives in semantic_or_groups.items():
        best = None
        for alternative in alternatives:
            text = (
                alternative.value if isinstance(alternative.value, str)
                else alternative.normalized_text
            )
            for item in evidence:
                sentence = _supports_semantic_requirement(
                    text,
                    str(item.get("text") or ""),
                    item.get("evidence_type"),
                    item.get("reranker_score"),
                )
                if sentence:
                    score = _semantic_support_score(text, sentence, item.get("evidence_type"))
                    if best is None or score > best[0]:
                        best = (score, alternative, {**item, "text": sentence,
                            "requirement": text, "requirement_id": alternative.id,
                            "group_id": group_id, "semantic_support_score": score})
        if best:
            supporting_evidence.append(best[2])
            for alternative in alternatives:
                matched_requirements.append({
                    "type": "semantic", "requirement_id": alternative.id,
                    "group_id": group_id,
                    "requirement": alternative.original_text,
                    "matched": alternative.id == best[1].id,
                    "relationship": "OR", "mandatory": alternative.mandatory,
                    "evidence": [best[2]] if alternative.id == best[1].id else [],
                })
        else:
            is_mandatory = any(alternative.mandatory for alternative in alternatives)
            if is_mandatory:
                semantic_failures.append({
                    "type": "SEMANTIC", "requirement_id": alternatives[0].id,
                    "group_id": group_id,
                    "required": [alternative.original_text for alternative in alternatives],
                    "reason": "No OR alternative has supporting evidence",
                })
            matched_requirements.extend({
                "type": "semantic", "requirement_id": alternative.id,
                "group_id": group_id, "requirement": alternative.original_text,
                "matched": False, "relationship": "OR",
                "mandatory": alternative.mandatory, "evidence": [],
            } for alternative in alternatives)

    for group_id, alternatives in mixed_or_groups.items():
        group_matches = []
        group_passed = False
        for alternative in alternatives:
            alternative_type = "semantic"
            passed = False
            matches = []
            alternative_evidence = []
            if "semantic_evidence_retrieval" in alternative.capabilities:
                text = alternative.value if isinstance(alternative.value, str) else alternative.normalized_text
                passed, _, alternative_evidence, matches = validate_semantic_requirements(
                    candidate_id=candidate_id,
                    semantic_requirements=[text],
                    evidence=evidence,
                )
            else:
                field = (alternative.field or "").casefold()
                value = alternative.value
                alternative_type = {"skill": "skill", "skills": "skill", "role": "role", "roles": "role"}.get(field, field)
                if field in {"skill", "skills"} and value:
                    requirement_filter = {"skills": [str(value)]}
                elif field in {"role", "roles"} and value:
                    requirement_filter = {"roles": [str(value)]}
                elif field == "company" and value:
                    requirement_filter = {"companies": [str(value)]}
                elif field == "location" and value:
                    requirement_filter = {"location": str(value)}
                else:
                    requirement_filter = {}
                if requirement_filter:
                    passed, _, matches, alternative_evidence = validate_structured_requirements(
                        db=db, candidate_id=candidate_id,
                        requirements=requirement_filter, evidence=evidence,
                    )
            group_passed = group_passed or passed
            group_matches.extend(alternative_evidence)
            selected = matches[0] if matches else {}
            if selected.get("evidence"):
                group_matches.extend(selected["evidence"])
            matched_requirements.append({
                **selected,
                "type": selected.get("type", alternative_type),
                "requirement_id": alternative.id,
                "group_id": group_id,
                "requirement": alternative.original_text,
                "matched": passed,
                "relationship": "OR",
                "mandatory": True,
                "evidence": selected.get("evidence", alternative_evidence if passed else []),
            })
        if not group_passed:
            semantic_failures.append({
                "type": "OR_GROUP",
                "group_id": group_id,
                "required": [item.original_text for item in alternatives],
                "reason": "No structured or semantic alternative in this OR group matched",
            })
        else:
            supporting_evidence.extend(group_matches)

    semantic_valid = not semantic_failures
    for requirement in requirements_graph:
        minimum_months = requirement.minimum_relevant_experience_months
        if minimum_months is None:
            continue

        semantic_text = (
            requirement.value
            if isinstance(requirement.value, str)
            else requirement.normalized_text
        )
        semantic_match = next(
            (
                item for item in matched_requirements
                if item.get("type") == "semantic"
                and _normalize(item.get("requirement")) == _normalize(semantic_text)
            ),
            None,
        )
        supporting_sources: dict[int, tuple[Experience, dict]] = {}
        for evidence_item in evidence:
            if str(evidence_item.get("evidence_type") or "").casefold() in {
                "skill", "skills", "education"
            }:
                continue
            passage = str(evidence_item.get("text") or "")
            matched_sentence = _supports_semantic_requirement(
                requirement=semantic_text,
                evidence_text=passage,
                evidence_type=evidence_item.get("evidence_type"),
                reranker_score=evidence_item.get("reranker_score"),
            )
            if not matched_sentence:
                continue
            source = _resolve_experience_source(db, candidate_id, evidence_item)
            if source is None:
                continue
            if _experience_duration_months(source) is not None:
                supporting_sources[source.id] = (
                    source,
                    {
                        **evidence_item,
                        "text": matched_sentence,
                        "source": _experience_source_label(source),
                        "experience_id": source.id,
                    },
                )

        actual_months = _combined_experience_months(
            [source for source, _ in supporting_sources.values()]
        )
        duration_matched = bool(supporting_sources) and actual_months >= minimum_months
        duration_label = (
            f"{minimum_months / 12:g} years relevant experience in {semantic_text}"
        )
        matched_requirements.append({
            "type": "relevant_experience",
            "requirement_id": requirement.id,
            "requirement": duration_label,
            "matched": duration_matched,
            "candidate_value": (
                f"{_format_months(actual_months)} dated role tenure"
                if supporting_sources
                else "No dated supporting experience found"
            ),
            "evidence": [proof for _, proof in supporting_sources.values()],
        })
        if semantic_match and supporting_sources:
            semantic_match["evidence"] = [
                proof for _, proof in supporting_sources.values()
            ][:1]
        if not duration_matched:
            semantic_valid = False
            semantic_failures.append({
                "type": "EXPERIENCE_SCOPE",
                "requirement_id": requirement.id,
                "required": duration_label,
                "reason": (
                    f"Only {_format_months(actual_months)} of dated experience supports this activity; "
                    f"at least {_format_months(minimum_months)} is required."
                    if supporting_sources
                    else "The semantic evidence could not be linked to dated experience records."
                ),
            })

    # Capture the current rule-based behavior for the evaluation baseline.
    # Candidate-level CrossEncoder validation is applied after this snapshot.
    legacy_semantic_valid = semantic_valid
    legacy_requirement_decisions = [{
        "requirement_id": match.get("requirement_id"),
        "requirement": match.get("requirement"),
        "matched": bool(match.get("matched")),
        "group_id": match.get("group_id"),
    } for match in matched_requirements if match.get("type") == "semantic"]
    legacy_decisions_by_id = {
        item.get("requirement_id"): item.get("matched")
        for item in legacy_requirement_decisions
    }
    candidate_semantic_failures = []
    candidate_semantic_valid = True
    if candidate_semantic_scores is not None:
        semantic_nodes = [
            item for item in requirements_graph
            if item.mandatory and "semantic_evidence_retrieval" in item.capabilities
        ]
        semantic_groups: dict[str, list] = {}
        nodes_by_id = {item.id: item for item in semantic_nodes}
        semantic_group_passes: dict[str, bool] = {}
        independent_nodes = []
        for node in semantic_nodes:
            if node.group_id and node.relationship.upper() == "OR":
                semantic_groups.setdefault(node.group_id, []).append(node)
            else:
                independent_nodes.append(node)

        def node_score(node):
            value = node.value if isinstance(node.value, str) else node.normalized_text
            return candidate_semantic_scores.get(_normalize(value),
                candidate_semantic_scores.get(_normalize(node.original_text)))

        stage_two_passes = [
            node_score(node) is not None
            and float(node_score(node)) >= candidate_semantic_min_score
            for node in independent_nodes
        ]
        for alternatives in semantic_groups.values():
            group_scores = [node_score(node) for node in alternatives]
            semantic_group_passed = any(
                score is not None and float(score) >= candidate_semantic_min_score
                for score in group_scores
            )
            group_id = alternatives[0].group_id
            structured_group_passed = any(
                match.get("group_id") == group_id
                and match.get("type") != "semantic"
                and match.get("matched")
                for match in matched_requirements
            )
            group_passed = semantic_group_passed or structured_group_passed
            semantic_group_passes[group_id] = group_passed
            stage_two_passes.append(group_passed)
        if semantic_nodes:
            candidate_semantic_valid = all(stage_two_passes)

        for match in matched_requirements:
            if match.get("type") != "semantic":
                continue
            requirement_text = str(match.get("requirement") or "")
            score = candidate_semantic_scores.get(_normalize(requirement_text))
            passed = score is not None and float(score) >= candidate_semantic_min_score
            match["candidate_reranker_score"] = score
            match["candidate_reranker_threshold"] = candidate_semantic_min_score
            match["candidate_validated"] = passed
            if match.get("matched") and not passed:
                match["matched"] = False
                node = nodes_by_id.get(match.get("requirement_id"))
                group_passed = bool(
                    node and node.group_id and node.relationship.upper() == "OR"
                    and semantic_group_passes.get(node.group_id)
                )
                if group_passed:
                    continue
                candidate_semantic_valid = False
                candidate_semantic_failures.append({
                    "type": "CANDIDATE_SEMANTIC",
                    "requirement_id": match.get("requirement_id"),
                    "group_id": match.get("group_id"),
                    "required": requirement_text,
                    "candidate_reranker_score": score,
                    "threshold": candidate_semantic_min_score,
                    "reason": (
                        "Candidate-level evidence score was below the configured relevance threshold."
                        if score is not None else
                        "No candidate-level evidence score was available for this requirement."
                    ),
                })
        for group_id, alternatives in semantic_groups.items():
            if not semantic_group_passes.get(group_id):
                continue
            passing_nodes = [node for node in alternatives
                if node_score(node) is not None
                and float(node_score(node)) >= candidate_semantic_min_score]
            if not passing_nodes:
                continue
            best_node = max(passing_nodes, key=lambda node: float(node_score(node)))
            selected_match = next((match for match in matched_requirements
                if match.get("requirement_id") == best_node.id), None)
            if selected_match:
                selected_match["matched"] = True
                selected_match["candidate_validated"] = True
        if candidate_semantic_failures:
            semantic_valid = False
            semantic_failures.extend(candidate_semantic_failures)

    evidence_validation_duration = perf_counter() - evidence_validation_started

    relational_started = perf_counter()
    relational_failures, relational_matches = validate_relational_requirements(
        db=db,
        candidate_id=candidate_id,
        requirements=requirements_graph,
        evidence=structured_evidence + supporting_evidence,
    )

    failures = (
        structured_failures
        + semantic_failures
        + relational_failures
    )

    all_evidence = []
    seen_evidence = set()
    for item in structured_evidence + supporting_evidence:
        key = (
            item.get("evidence_type"),
            item.get("source_id") or item.get("evidence_id"),
            _normalize(item.get("text")),
        )
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        all_evidence.append(item)

    matched_requirements.extend(relational_matches)

    temporal_started = perf_counter()
    temporal_failures, temporal_matches = validate_temporal_requirements(
        db=db,
        candidate_id=candidate_id,
        requirements=requirements_graph,
        evidence=structured_evidence + supporting_evidence,
    )
    failures.extend(temporal_failures)
    matched_requirements.extend(temporal_matches)

    # Preserve the pre-candidate-CE match state for an honest shadow baseline.
    baseline_matched_requirements = []
    for match in matched_requirements:
        baseline_match = dict(match)
        if match.get("type") == "semantic":
            baseline_match["matched"] = bool(legacy_decisions_by_id.get(
                match.get("requirement_id"), match.get("matched")
            ))
            baseline_match.pop("candidate_reranker_score", None)
            baseline_match.pop("candidate_reranker_threshold", None)
            baseline_match.pop("candidate_validated", None)
        baseline_matched_requirements.append(baseline_match)

    soft_nodes = [item for item in requirements_graph
        if not item.mandatory and "semantic_evidence_retrieval" in item.capabilities]
    for requirement in soft_nodes:
        requirement_text = str(requirement.value or requirement.normalized_text)
        key = _normalize(requirement_text)
        score = (soft_semantic_scores or {}).get(key)
        matched = score is not None and float(score) >= candidate_semantic_min_score
        matched_requirements.append({
            "type": "semantic",
            "requirement_id": requirement.id,
            "group_id": requirement.group_id,
            "relationship": requirement.relationship,
            "match_mode": "SOFT",
            "mandatory": False,
            "requirement": requirement.original_text,
            "matched": matched,
            "candidate_reranker_score": score,
            "candidate_reranker_threshold": candidate_semantic_min_score,
            "candidate_validated": matched,
            "candidate_value": "Supported by consolidated resume evidence" if matched else None,
            "evidence": ((soft_semantic_evidence or {}).get(key, [])[:2] if matched else []),
        })

    requirement_statuses = []
    for requirement in requirements_graph:
        linked = [match for match in matched_requirements
            if match.get("requirement_id") == requirement.id]
        if not linked:
            wanted = _normalize(str(requirement.value or requirement.original_text))
            linked = [match for match in matched_requirements
                if _normalize(str(match.get("requirement") or "")) == wanted]
        if not linked:
            field = (requirement.field or "").casefold()
            expected_type = {
                "skill": "skill", "skills": "skill", "role": "role", "roles": "role",
                "company": "company", "companies": "company", "location": "location",
                "experience": "experience", "total_experience": "experience",
                "min_experience_years": "experience", "max_experience_years": "experience",
            }.get(field)
            if expected_type:
                linked = [match for match in matched_requirements
                    if match.get("type") == expected_type]
        matched = any(bool(match.get("matched")) for match in linked)
        if requirement.group_id and requirement.relationship.upper() == "OR":
            group_nodes = [node for node in requirements_graph
                if node.group_id == requirement.group_id and node.relationship.upper() == "OR"]
            group_matches = [match for node in group_nodes for match in matched_requirements
                if match.get("requirement_id") == node.id]
            matched = any(bool(match.get("matched")) for match in group_matches)
        match_mode = requirement.match_mode or ("HARD" if requirement.mandatory else "SOFT")
        status = "MATCH" if matched else ("NO_MATCH" if match_mode == "HARD" else "PARTIAL_MATCH")
        requirement_statuses.append({
            "requirement_id": requirement.id,
            "requirement": requirement.original_text,
            "match_mode": match_mode,
            "matched": matched,
            "status": status,
        })
        for match in linked:
            match["match_mode"] = match_mode
            match["mandatory"] = match_mode == "HARD"
            match.setdefault("requirement_id", requirement.id)

    partial_match = any(
        status["match_mode"] == "SOFT" and status["status"] == "PARTIAL_MATCH"
        for status in requirement_statuses
    )
    match_status = "NO_MATCH" if not (
        structured_valid and semantic_valid and not relational_failures and not temporal_failures
    ) else "PARTIAL_MATCH" if partial_match else "MATCH"

    return {
        "candidate_id": candidate_id,
        "valid": structured_valid and semantic_valid and not relational_failures and not temporal_failures,
        "baseline_valid": structured_valid and legacy_semantic_valid and not relational_failures and not temporal_failures,
        "candidate_semantic_valid": candidate_semantic_valid,
        "match_status": match_status,
        "requirement_statuses": requirement_statuses,
        "baseline_requirement_decisions": legacy_requirement_decisions,
        "baseline_matched_requirements": baseline_matched_requirements,
        "failures": failures,
        "supporting_evidence": all_evidence,
        "structured_matches": [
            f"{item['type'].title()}: {item.get('candidate_value')}"
            for item in structured_matches
        ],
        "matched_requirements": matched_requirements,
        "temporal_duration_seconds": perf_counter() - temporal_started,
        "relational_duration_seconds": perf_counter() - relational_started,
        "evidence_validation_duration_seconds": evidence_validation_duration,
        "qualification_duration_seconds": qualification_duration,
    }


def _normalize_for_source(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _resolve_experience_source(db: Session, candidate_id: int, evidence: dict):
    """Resolve an evidence passage only when it directly matches a dated experience."""
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

    # Parsed experience descriptions can differ slightly from the original
    # resume section. Link only when the evidence passage strongly and
    # uniquely overlaps one dated role description.
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


def validate_relational_requirements(
    db: Session,
    candidate_id: int,
    requirements: list,
    evidence: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Resolve SAME_SOURCE relationships over already validated evidence."""
    by_id = {item.id: item for item in requirements}
    failures = []
    matches = []
    for requirement in requirements:
        if requirement.relationship.upper() != "SAME_SOURCE":
            continue
        source_sets = []
        for dependency_id in requirement.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                source_sets.append(set())
                continue
            expected = _normalize_for_source(
                str(dependency.value) if isinstance(dependency.value, str)
                else dependency.normalized_text
            )
            sources = set()
            for item in evidence:
                if _normalize_for_source(item.get("requirement")) != expected:
                    continue
                if item.get("source_kind") == "experience_record":
                    sources.add(("experience", item.get("experience_id")))
                else:
                    resolved = _resolve_experience_source(db, candidate_id, item)
                    if resolved is not None:
                        sources.add(("experience", resolved.id))
                    elif item.get("source_id") is not None:
                        sources.add(("evidence", item.get("source_id")))
            source_sets.append(sources)
        common_sources = (
            set.intersection(*source_sets)
            if source_sets and all(source_sets)
            else set()
        )
        matched = bool(common_sources)
        if not matched and requirement.mandatory:
            failures.append({
                "type": "RELATIONAL", "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": "Dependent requirements could not be resolved to the same evidence source",
            })
        matches.append({
            "type": "relational", "requirement_id": requirement.id,
            "requirement": requirement.original_text, "matched": matched,
            "relationship": "SAME_SOURCE", "evidence": [],
        })
    return failures, matches


def validate_temporal_requirements(
    db: Session,
    candidate_id: int,
    requirements: list,
    evidence: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Validate time only against the dated source for its dependency evidence."""
    by_id = {item.id: item for item in requirements}
    failures = []
    matches = []
    today = date.today()
    for requirement in requirements:
        if requirement.type != "TEMPORAL":
            continue
        dependency_evidence = []
        for dependency_id in requirement.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                continue
            expected_text = _normalize_for_source(
                str(dependency.value or dependency.normalized_text)
            )
            dependency_evidence.extend(
                item for item in evidence
                if _normalize_for_source(item.get("requirement")) == expected_text
            )
        if not dependency_evidence:
            # The activity itself did not qualify, so its date cannot be
            # evaluated. Keep this as a dependent non-match instead of adding
            # a second, misleading hard failure for missing dates.
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": False,
                "reason": "No supporting activity evidence to date",
                "evidence": [],
            })
            continue
        sources = [
            _resolve_experience_source(db, candidate_id, item)
            for item in dependency_evidence
        ]
        sources = [source for source in sources if source is not None]
        within_months = requirement.temporal_window_months
        valid_source = None
        if within_months is not None:
            cutoff = today - timedelta(days=within_months * 30)
            for source in sources:
                activity_end = today if source.is_current else source.end_date
                if activity_end is not None and activity_end >= cutoff:
                    valid_source = source
                    break
        if valid_source is None:
            temporal_failure = {
                "type": "TEMPORAL",
                "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": "Matched evidence could not be linked to a dated source within the requested time window",
            }
            if requirement.mandatory:
                failures.append(temporal_failure)
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": False, "evidence": [],
            })
        else:
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": True,
                "candidate_value": valid_source.end_date.isoformat() if valid_source.end_date else "ongoing",
                "evidence": dependency_evidence,
            })
    return failures, matches
