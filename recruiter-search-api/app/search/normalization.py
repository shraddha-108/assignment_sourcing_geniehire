"""Requirement-level canonicalization and bounded query expansion."""

from __future__ import annotations

import re

from app.search.schema import SearchRequirement


_ROLE_GROUPS = (
    ("software engineer", "sde", "software development engineer", "software developer"),
    ("machine learning engineer", "ml engineer", "machine-learning engineer"),
    ("react developer", "react dev", "react.js developer", "reactjs developer"),
)
_SKILL_GROUPS = (
    ("javascript", "js"),
    ("postgresql", "postgres", "postgre sql"),
    ("react", "react.js", "reactjs"),
    ("java",),
    ("python",),
)

# These are retrieval synonyms, not separate required criteria. The original
# requirement always remains the CrossEncoder validation query.
_SEMANTIC_CONCEPTS = {
    "financial transformation": (
        "finance transformation", "finance process optimization",
        "financial process optimization", "finance process improvement",
    ),
    "machine learning projects": (
        "ML projects", "applied machine learning projects",
    ),
    "AI products": (
        "AI-powered products", "production AI applications",
    ),
    "SAP implementation": (
        "SAP rollout", "implementing SAP solutions",
    ),
    "AWS migration": (
        "Amazon Web Services migration", "migrating workloads to AWS",
    ),
    "Microsoft ecosystem": (
        "Dynamics 365 or D365", "Power Platform", "Azure",
        "Microsoft 365 or Office 365", "SharePoint", "Teams", ".NET or C#",
        "SQL Server", "Entra ID",
    ),
    "cloud technologies": (
        "AWS", "Microsoft Azure", "Google Cloud", "Oracle Cloud",
        "cloud infrastructure", "containers", "Kubernetes", "serverless",
        "infrastructure as code",
    ),
    "backend technologies": (
        "server-side development", "backend languages and frameworks",
        "REST or GraphQL APIs", "databases", "microservices",
    ),
}
_FAMILY_QUERY_PATTERNS = {
    "microsoft ecosystem": r"\bmicrosoft\s+(?:technology|technologies|ecosystem|stack)\b",
    "cloud technologies": r"\bcloud\s+(?:technology|technologies|ecosystem|platforms?)\b",
    "backend technologies": r"\bback[- ]end\s+(?:tech|technolog(?:y|ies|ical))\b",
}
_SEMANTIC_CONCEPT_PATTERNS = {
    "financial transformation": r"\b(?:financial|finance)\s+transformation\b|\b(?:finance|financial)\s+process\s+(?:optimization|improvement)\b",
    "machine learning projects": r"\b(?:machine\s+learning|ML)\s+projects?\b",
    "AI products": (
        r"\bAI[- ](?:powered\s+)?products?\b|"
        r"\bproducts?\s+(?:(?:built|created|developed)\s+)?(?:with|using)\s+AI\b|"
        r"\b(?:built|created|developed)\s+AI\s+products?\b"
    ),
    "SAP implementation": r"\bSAP\s+(?:implementation|implementations|rollout)\b|\bimplement\w*.{0,32}\bSAP\b|\bSAP\b.{0,32}\bimplement\w*",
    "AWS migration": r"\b(?:AWS|Amazon\s+Web\s+Services)\s+migrations?\b",
    "Microsoft ecosystem": _FAMILY_QUERY_PATTERNS["microsoft ecosystem"],
    "cloud technologies": _FAMILY_QUERY_PATTERNS["cloud technologies"],
    "backend technologies": _FAMILY_QUERY_PATTERNS["backend technologies"],
}
_INDUSTRY_EVIDENCE_TERMS = {
    "it": (
        "information technology", "it services", "software", "technology",
        "saas", "cybersecurity", "telecommunications", "cloud computing",
    ),
    "information technology": (
        "information technology", "it services", "software", "technology",
        "saas", "cybersecurity", "telecommunications", "cloud computing",
    ),
    "healthcare": ("healthcare", "health care", "hospital", "clinical", "medical", "pharmaceutical"),
    "pharmaceutical": ("pharmaceutical", "pharma", "biotechnology", "clinical"),
    "finance": ("financial services", "banking", "investment", "insurance", "fintech"),
    "financial services": ("financial services", "banking", "investment", "insurance", "fintech"),
    "manufacturing": ("manufacturing", "industrial", "production plant", "factory"),
    "retail": ("retail", "e-commerce", "ecommerce", "consumer goods"),
}

_SOFT_PREFIX = re.compile(
    r"\b(?:preferably|preferred|ideally|nice\s+to\s+have|nice-to-have|"
    r"bonus(?:\s+if)?|optional|would\s+be\s+good\s+to\s+have)\b\s*"
    r"(?P<term>[^,;.!?]+)", re.IGNORECASE,
)
_SOFT_SUFFIX = re.compile(
    r"\b(?P<term>[\w.+#/-]+)\s+"
    r"(?:(?:is|would\s+be)\s+)?(?:a\s+)?(?:plus|bonus|preferred)\b",
    re.IGNORECASE,
)


def normalize_phrase(value: str | None) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def industry_evidence_terms(requirement: str) -> tuple[str, ...]:
    """Return conservative evidence cues for an explicitly named industry."""
    match = re.search(
        r"\b(?P<domain>[a-z0-9][a-z0-9 &/-]*?)\s+(?:industry|sector|domain)\b",
        normalize_phrase(requirement),
    )
    if not match:
        return ()
    domain = " ".join(match.group("domain").split())
    return _INDUSTRY_EVIDENCE_TERMS.get(domain, (domain,))


def industry_evidence_matches(text: str, requirement: str) -> bool:
    """Match industry cues in evidence or an employer name, including common typos."""
    terms = industry_evidence_terms(requirement)
    if not terms:
        return False
    normalized_text = normalize_phrase(text)
    for term in terms:
        if re.search(rf"(?<![\w]){re.escape(normalize_phrase(term))}(?![\w])", normalized_text):
            return True
    # Handle misspelled employer names such as "technonologies" while keeping
    # the match scoped to the distinctive technology stem.
    return bool(
        "technology" in terms
        and re.search(r"\btech\w{0,6}nolog(?:y|ies)\b", normalized_text)
    )


def _alias_group(value: str, kind: str) -> tuple[str, ...]:
    normalized = normalize_phrase(value)
    groups = _ROLE_GROUPS if kind == "role" else _SKILL_GROUPS if kind == "skill" else ()
    for group in groups:
        if any(normalize_phrase(alias) == normalized for alias in group):
            return group
    if len(normalized) >= 5:
        max_distance = 1 if len(normalized) < 9 else 2
        candidates = []
        for group in groups:
            distance = min(_edit_distance(normalized, normalize_phrase(alias)) for alias in group)
            if distance <= max_distance:
                candidates.append((distance, group))
        if candidates:
            best_distance = min(distance for distance, _ in candidates)
            best_groups = {tuple(group) for distance, group in candidates if distance == best_distance}
            if len(best_groups) == 1:
                return next(iter(best_groups))
    return (value.strip(),) if value and value.strip() else ()


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def equivalent_terms(value: str, kind: str) -> list[str]:
    """Return exact-equivalence terms only; no substring or family expansion."""
    group = _alias_group(value, kind)
    if not group:
        return []
    canonical = group[0]
    return list(dict.fromkeys([canonical, *group]))


def canonical_term(value: str, kind: str) -> str:
    group = _alias_group(value, kind)
    return group[0] if group else " ".join(str(value or "").split())


def _soft_clauses(query: str) -> list[str]:
    return [match.group("term").strip() for pattern in (_SOFT_PREFIX, _SOFT_SUFFIX)
            for match in pattern.finditer(query)]


def requirement_kind(requirement) -> str | None:
    field = (requirement.field or "").casefold()
    source = (requirement.source_of_truth or "").casefold()
    if field in {"role", "roles"} or "role" in source:
        return "role"
    if field in {"skill", "skills"} or "skill" in source:
        return "skill"
    return None


def _mentioned_in_clause(requirement, clause: str) -> bool:
    value = requirement.value if isinstance(requirement.value, str) else requirement.original_text
    kind = requirement_kind(requirement) or ""
    aliases = equivalent_terms(str(value or requirement.original_text), kind) if kind else []
    probes = [str(value or ""), requirement.original_text, *aliases]
    clause_norm = normalize_phrase(clause)
    if any(
        probe and re.search(rf"(?<![\w+#]){re.escape(normalize_phrase(probe))}(?![\w+#])", clause_norm)
        for probe in probes
    ):
        return True
    clause_tokens = set(re.findall(r"[a-z0-9+#.]+", clause_norm))
    requirement_tokens = set(re.findall(
        r"[a-z0-9+#.]+", normalize_phrase(str(value or requirement.original_text))
    ))
    return bool(clause_tokens and requirement_tokens and
                len(clause_tokens & requirement_tokens) / len(requirement_tokens) >= 0.6)


def explicit_soft_requirement_ids(query: str, requirements: list) -> set[str]:
    """Associate explicit preference wording with the extracted requirement(s)."""
    clauses = _soft_clauses(query)
    return {
        requirement.id for requirement in requirements
        if any(_mentioned_in_clause(requirement, clause) for clause in clauses)
    }


def expand_semantic_requirement(requirement: str) -> str:
    """Add related retrieval language while retaining the intact requirement."""
    expansions: list[str] = []
    for concept, synonyms in _SEMANTIC_CONCEPTS.items():
        pattern = _SEMANTIC_CONCEPT_PATTERNS.get(
            concept, rf"(?<!\w){re.escape(normalize_phrase(concept))}(?!\w)"
        )
        if re.search(pattern, requirement, re.IGNORECASE):
            expansions.extend(synonyms)
    industry_terms = industry_evidence_terms(requirement)
    if industry_terms:
        expansions.extend(industry_terms)
    if not expansions:
        return requirement
    unique = list(dict.fromkeys(expansions))
    return (
        f"{requirement}. Related retrieval terminology (alternatives, not extra requirements): "
        + "; ".join(unique)
    )


def ensure_semantic_family_requirements(query: str, parsed_query) -> list[str]:
    """Retain recognized broad technology families if the parser omitted them."""
    assumptions = []
    for index, (canonical, pattern) in enumerate(_FAMILY_QUERY_PATTERNS.items(), start=1):
        if not re.search(pattern, query, re.IGNORECASE):
            continue
        already_represented = any(
            re.search(pattern, str(value), re.IGNORECASE)
            for value in parsed_query.semantic_requirements
        ) or any(
            "semantic_evidence_retrieval" in item.capabilities
            and re.search(pattern, item.original_text, re.IGNORECASE)
            for item in parsed_query.requirements
        )
        if already_represented:
            continue
        parsed_query.semantic_requirements.append(canonical)
        parsed_query.requirements.append(SearchRequirement(
            id=f"semantic_family_{index}",
            original_text=canonical,
            normalized_text=canonical,
            type="SEMANTIC",
            mandatory=True,
            source_of_truth="resume_evidence",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
            field="semantic_requirements",
            value=canonical,
            confidence=0.85,
        ))
        assumptions.append(
            f"{canonical.title()} is treated as one broad requirement; relevant evidence for a related product or area may support it."
        )
    return assumptions


def normalize_explicit_semantic_or(query: str, requirements: list, semantic_requirements: list[str]) -> list[str]:
    """Split explicit semantic disjunctions and retain each alternative as an OR node.

    Structured skill nodes mentioned in one alternative join the same group. This
    lets qualification accept evidence from either the semantic or structured
    path instead of accidentally requiring both paths to pass.
    """
    combined_nodes = [
        item for item in requirements
        if ("semantic_evidence_retrieval" in item.capabilities or item.type.upper() == "SEMANTIC")
        and isinstance(item.value, str)
        and re.search(r"\s+or\s+", item.value, re.IGNORECASE)
    ]
    if not combined_nodes:
        return semantic_requirements

    node = combined_nodes[0]
    raw_alternatives = re.split(r"\s+or\s+", node.value, flags=re.IGNORECASE)
    alternatives = []
    for raw in raw_alternatives:
        clause = " ".join(raw.strip(" ,.;?!").split())
        clause = re.sub(r"^(?:candidates?\s+)?(?:who|that)\s+(?:(?:has|have|had)\s+)?", "", clause, flags=re.IGNORECASE)
        clause = re.sub(r"^(?:candidates?\s+)", "", clause, flags=re.IGNORECASE)
        if clause:
            alternatives.append(clause)
    if len(alternatives) < 2:
        return semantic_requirements

    group_id = f"explicit_or_{node.id}"
    requirements[:] = [item for item in requirements if item not in combined_nodes]
    for index, clause in enumerate(alternatives, start=1):
        requirements.append(SearchRequirement(
            id=f"{group_id}_semantic_{index}",
            original_text=clause,
            normalized_text=normalize_phrase(clause),
            type="SEMANTIC",
            mandatory=True,
            match_mode="HARD",
            source_of_truth="resume_evidence",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
            group_id=group_id,
            relationship="OR",
            field="semantic_requirements",
            value=clause,
            confidence=node.confidence,
        ))
        # A structured skill explicitly named by this branch is a valid
        # structured alternative in the same disjunction.
        mentioned = [
            item for item in requirements
            if item.type.upper() == "STRUCTURED"
            and (item.field or "").casefold() in {"skill", "skills"}
            and isinstance(item.value, str)
            and any(
                re.search(rf"(?<![\w+#]){re.escape(normalize_phrase(alias))}(?![\w+#])",
                          normalize_phrase(clause))
                for alias in equivalent_terms(item.value, "skill")
            )
        ]
        if len(mentioned) == 1:
            mentioned[0].group_id = group_id
            mentioned[0].relationship = "OR"

    return [
        value for value in semantic_requirements
        if normalize_phrase(value) != normalize_phrase(node.value)
    ] + alternatives


def parse_explicit_experience_bounds(query: str) -> dict | None:
    """Read explicit years bounds without broadening or rounding the request."""
    range_match = re.search(
        r"\b(?P<low>\d+(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to)\s*"
        r"(?P<high>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\b",
        query, re.IGNORECASE,
    )
    if range_match:
        low, high = float(range_match.group("low")), float(range_match.group("high"))
        if low <= high:
            return {"min_experience_years": low, "max_experience_years": high,
                    "min_experience_exclusive": False}

    greater_match = re.search(
        r"\b(?:more\s+than|over)\s+(?P<years>\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
        query, re.IGNORECASE,
    )
    minimum_match = re.search(
        r"\b(?:at\s+least|minimum(?:\s+of)?|no\s+less\s+than)\s+"
        r"(?P<years>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\b|"
        r"\b(?P<plus>\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)\b",
        query, re.IGNORECASE,
    )
    maximum_match = re.search(
        r"\b(?:up\s+to|at\s+most|maximum(?:\s+of)?|no\s+more\s+than)\s+"
        r"(?P<years>\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
        query, re.IGNORECASE,
    )
    if greater_match:
        return {"min_experience_years": float(greater_match.group("years")),
                "max_experience_years": None, "min_experience_exclusive": True}
    if minimum_match:
        years = minimum_match.group("years") or minimum_match.group("plus")
        return {"min_experience_years": float(years), "max_experience_years": None,
                "min_experience_exclusive": False}
    if maximum_match:
        return {"min_experience_years": None,
                "max_experience_years": float(maximum_match.group("years")),
                "min_experience_exclusive": False}
    return None
