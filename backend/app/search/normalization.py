"""Requirement-level canonicalization and bounded query expansion."""

from __future__ import annotations

import re

from app.search.schema import SearchRequirement


_ROLE_GROUPS = (
    ("software engineer", "sde", "software development engineer", "software developer"),
    ("machine learning engineer", "ml engineer", "machine-learning engineer"),
    ("react developer", "react dev", "react.js developer", "reactjs developer"),
    (
        "backend developer",
        "back end developer",
        "back-end developer",
        "backend engineer",
        "back end engineer",
        "back-end engineer",
        "backend software developer",
        "back end software developer",
        "back-end software developer",
        "backend software engineer",
        "back end software engineer",
        "back-end software engineer",
        "software developer backend",
        "software engineer backend",
        "server-side developer",
        "server side developer",
        "server-side engineer",
        "server side engineer",
    ),
    (
        "frontend developer",
        "front end developer",
        "front-end developer",
        "frontend engineer",
        "front end engineer",
        "front-end engineer",
        "frontend software developer",
        "front end software developer",
        "front-end software developer",
        "frontend software engineer",
        "front end software engineer",
        "front-end software engineer",
        "software developer frontend",
        "software engineer frontend",
    ),
    (
        "cloud developer",
        "cloud software developer",
        "cloud platform developer",
        "cloud engineer",
        "cloud software engineer",
        "cloud platform engineer",
        "software developer cloud",
        "software engineer cloud",
    ),
    (
        "sales executive",
        "sales representative",
        "sales rep",
        "sales associate",
        "sales specialist",
        "sales consultant",
        "inside sales executive",
        "inside sales representative",
        "inside sales",
        "business development executive",
        "bde",
        "business development representative",
        "bdr",
        "sales development representative",
        "sdr",
        "account executive",
        "sales manager",
    ),
    (
        "hr",
        "human resources",
        "human resource",
        "hr executive",
        "hr associate",
        "hr specialist",
        "hr generalist",
        "hr recruiter",
        "hr officer",
        "hr consultant",
        "talent acquisition",
        "talent acquisition specialist",
        "talent acquisition executive",
        "talent acquisition associate",
        "technical recruiter",
        "it recruiter",
        "recruiter",
        "recruitment specialist",
        "recruitment executive",
        "recruitment associate",
    ),
    (
        "qa engineer",
        "qa",
        "quality assurance engineer",
        "quality assurance",
        "qa tester",
        "qa analyst",
        "automation test engineer",
        "automation tester",
        "test engineer",
        "software test engineer",
        "software tester",
        "sdet",
        "qa automation engineer",
    ),
)
_SKILL_GROUPS = (
    ("javascript", "js"),
    ("postgresql", "postgres", "postgre sql"),
    ("react", "react.js", "reactjs"),
    ("java",),
    ("python",),
    ("ai", "artificial intelligence", "genai", "generative ai", "llm", "llms", "rag", "machine learning", "ml"),
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
    "artificial intelligence": (
        "AI", "machine learning", "deep learning", "generative AI", "GenAI",
        "LLMs", "RAG", "prompt engineering", "neural networks", "vector databases",
        "embeddings", "NLP", "computer vision",
    ),
    "machine learning": (
        "ML", "deep learning", "supervised learning", "unsupervised learning",
        "neural networks", "PyTorch", "TensorFlow", "Scikit-Learn", "model training",
        "predictive modeling", "feature engineering",
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
    "customer relationship management": (
        "CRM", "client relationship management", "account management",
        "client relationships", "relationship manager", "account manager", "customer success",
        "customer engagement", "customer retention", "Salesforce",
        "HubSpot", "Microsoft Dynamics 365", "Zoho CRM",
    ),
}
_FAMILY_QUERY_PATTERNS = {
    "microsoft ecosystem": r"\bmicrosoft\s+(?:technology|technologies|ecosystem|stack)\b",
    "cloud technologies": r"\bcloud\s+(?:technology|technologies|ecosystem|platforms?)\b",
    "backend technologies": r"\bback[- ]?end\s+(?:tech|technolog(?:y|ies|ical))\b",
    "artificial intelligence": r"\b(?:artificial\s+intelligence|\bAI\b|genai|generative\s+ai)\b",
    "machine learning": r"\b(?:machine\s+learning|\bML\b)\b",
}
_SEMANTIC_CONCEPT_PATTERNS = {
    "financial transformation": r"\b(?:financial|finance)\s+transformation\b|\b(?:finance|financial)\s+process\s+(?:optimization|improvement)\b",
    "machine learning projects": r"\b(?:machine\s+learning|ML)\s+projects?\b",
    "AI products": (
        r"\bAI[- ](?:powered\s+)?products?\b|"
        r"\bproducts?\s+(?:(?:built|created|developed)\s+)?(?:with|using)\s+AI\b|"
        r"\b(?:built|created|developed)\s+AI\s+products?\b"
    ),
    "artificial intelligence": _FAMILY_QUERY_PATTERNS["artificial intelligence"],
    "machine learning": _FAMILY_QUERY_PATTERNS["machine learning"],
    "SAP implementation": r"\bSAP\s+(?:implementation|implementations|rollout)\b|\bimplement\w*.{0,32}\bSAP\b|\bSAP\b.{0,32}\bimplement\w*",
    "AWS migration": r"\b(?:AWS|Amazon\s+Web\s+Services)\s+migrations?\b",
    "Microsoft ecosystem": _FAMILY_QUERY_PATTERNS["microsoft ecosystem"],
    "cloud technologies": _FAMILY_QUERY_PATTERNS["cloud technologies"],
    "backend technologies": _FAMILY_QUERY_PATTERNS["backend technologies"],
    "customer relationship management": (
        r"\b(?:customer|client)\s+relationship\s+management\b|"
        r"\bCRM\b|\baccount\s+management\b|\brelationship\s+manager\b|"
        r"\baccount\s+manager\b|\bclient\s+relationships?\b|"
        r"\bcustomer\s+(?:success|engagement|retention)\b|"
        r"\b(?:salesforce|hubspot|dynamics\s*365|zoho\s*crm)\b"
    ),
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


def canonicalize_semantic_requirement(requirement: str) -> str:
    """Keep retrieval wording stable for singular and plural ML project requests."""
    return re.sub(
        r"\b(machine[- ]learning|deep[- ]learning|ml)\s+projects?\b",
        lambda match: f"{match.group(1)} projects",
        requirement,
        flags=re.IGNORECASE,
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
        norm_tokens = normalized.split()
        for group in groups:
            for alias in group:
                norm_alias = normalize_phrase(alias)
                alias_tokens = norm_alias.split()
                if len(norm_tokens) != len(alias_tokens):
                    continue
                # Acronyms or short tokens (<= 3 chars, e.g. qa, ml, hr, ai) must match exactly
                if any(len(nt) <= 3 and nt != at for nt, at in zip(norm_tokens, alias_tokens)):
                    continue
                distance = _edit_distance(normalized, norm_alias)
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


def company_name_matches(actual: str | None, equivalents: list[str]) -> bool:
    """Match exact company aliases, including an acronym in a trailing parenthesis."""
    if not actual:
        return False

    def normalize_company(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

    actual_name = normalize_company(actual)
    if any(normalize_company(alias) == actual_name for alias in equivalents if alias):
        return True

    without_parenthetical = re.sub(r"\s*\([^()]*\)\s*$", "", actual).strip()
    return bool(
        without_parenthetical
        and normalize_company(without_parenthetical) != actual_name
        and any(
            normalize_company(alias) == normalize_company(without_parenthetical)
            for alias in equivalents if alias
        )
    )


_ROLE_LEVEL_MODIFIERS = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff",
    "associate", "trainee", "intern", "i", "ii", "iii", "iv", "v",
    "1", "2", "3", "4", "5",
    "executive", "specialist", "officer", "coordinator", "consultant",
    "generalist", "manager", "assistant", "representative", "rep",
}
_ROLE_DOMAIN_EXCLUSIONS = {
    "test", "testing", "qa", "quality", "assurance", "automation",
}


_META_ROLE_WORDS = {
    "candidate", "candidates", "profile", "profiles", "talent",
    "person", "people", "hire", "hires", "professional", "professionals",
}


def role_matches(requested_role: str, actual_role: str | None) -> bool:
    """Match explicit role families and their controlled title equivalents."""
    requested_tokens = re.findall(r"[a-z0-9+#.]+", (requested_role or "").casefold())
    actual_tokens = re.findall(r"[a-z0-9+#.]+", (actual_role or "").casefold())
    if not requested_tokens or not actual_tokens:
        return False

    actual_token_set = set(actual_tokens)
    cleaned_requested_tokens = [t for t in requested_tokens if t not in _META_ROLE_WORDS]
    effective_tokens = cleaned_requested_tokens or requested_tokens
    effective_role = " ".join(effective_tokens)

    if effective_tokens == ["developer"]:
        return (
            "developer" in actual_token_set
            and not actual_token_set & _ROLE_DOMAIN_EXCLUSIONS
        )

    if effective_tokens in (["sales"], ["salesperson"]):
        if "sales" in actual_token_set or "presales" in actual_token_set:
            return True
        if "business" in actual_token_set and "development" in actual_token_set:
            return True
        if "account" in actual_token_set and ("executive" in actual_token_set or "manager" in actual_token_set):
            if not (actual_token_set & {"payable", "receivable", "receivables", "audit", "tax", "accountant", "accounting"}):
                return True
        return False

    if effective_tokens in (["hr"], ["human", "resources"], ["human", "resource"]):
        if "hr" in actual_token_set:
            return True
        if "human" in actual_token_set and ("resource" in actual_token_set or "resources" in actual_token_set):
            return True
        if "recruiter" in actual_token_set or "recruitment" in actual_token_set or "recruiting" in actual_token_set:
            return True
        if "talent" in actual_token_set and ("acquisition" in actual_token_set or "recruiter" in actual_token_set):
            return True
        return False

    if effective_tokens in (["recruiter"], ["recruitment"], ["talent", "acquisition"]):
        if "recruiter" in actual_token_set or "recruitment" in actual_token_set or "recruiting" in actual_token_set:
            return True
        if "talent" in actual_token_set and "acquisition" in actual_token_set:
            return True
        if "hr" in actual_token_set:
            return True
        return False

    is_qa_query = any(tok in ("qa", "quality", "assurance", "test", "testing", "tester", "sdet") for tok in effective_tokens)
    if is_qa_query:
        if "qa" in actual_token_set or "sdet" in actual_token_set:
            return True
        if "test" in actual_token_set or "testing" in actual_token_set or "tester" in actual_token_set:
            return True
        if "quality" in actual_token_set and "assurance" in actual_token_set:
            return True
        return False

    aliases = list(dict.fromkeys(
        (equivalent_terms(effective_role, "role") or [])
        + (equivalent_terms(requested_role, "role") or [])
        + [effective_role, requested_role]
    ))
    for alias in aliases:
        alias_tokens = re.findall(r"[a-z0-9+#.]+", alias.casefold())
        if not alias_tokens:
            continue
        width = len(alias_tokens)
        if not any(
            actual_tokens[index:index + width] == alias_tokens
            for index in range(len(actual_tokens) - width + 1)
        ):
            continue

        extra_tokens = actual_token_set - set(alias_tokens)
        if (
            (is_qa_query or not extra_tokens & _ROLE_DOMAIN_EXCLUSIONS)
            and extra_tokens <= _ROLE_LEVEL_MODIFIERS
        ):
            return True

    return False


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
    requirement = canonicalize_semantic_requirement(requirement)
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
        # A broad technology family is a semantic evidence request, not one
        # literal skill. Remove only the family phrase itself if the parser
        # also placed it in a structured skills field; keep concrete skills
        # mentioned alongside it.
        parsed_query.skills[:] = [
            skill for skill in parsed_query.skills
            if not re.search(pattern, str(skill), re.IGNORECASE)
        ]
        parsed_query.requirements[:] = [
            requirement for requirement in parsed_query.requirements
            if not (
                requirement_kind(requirement) != "role"
                and (requirement.field or "").casefold() not in {"role", "roles", "experience", "total_experience", "seniority"}
                and (
                    requirement_kind(requirement) == "skill"
                    or (requirement.field or "").casefold() in {"skill", "skills", "technologies", "technology"}
                    or requirement.type.upper() == "STRUCTURED"
                )
                and re.search(
                    pattern,
                    str(requirement.value or requirement.original_text),
                    re.IGNORECASE,
                )
            )
        ]
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


def apply_explicit_boolean_operators(query: str, requirements: list) -> None:
    """Apply explicit OR and NOT connectors between parsed requirement spans."""
    for requirement in requirements:
        group_id = str(requirement.group_id or "")
        if group_id and not group_id.startswith("explicit_or_"):
            requirement.group_id = None
            if requirement.relationship.upper() == "OR":
                requirement.relationship = "AND"

    mentions = []
    for requirement in requirements:
        probes = [
            str(requirement.value) if isinstance(requirement.value, str) else "",
            requirement.original_text,
            requirement.normalized_text,
        ]
        matches = []
        structured = bool(set(requirement.capabilities) & {
            "structured_candidate_lookup", "structured_experience_lookup"
        })
        has_boolean_clause = structured and any(
            re.search(r"\b(?:and|or)\b", probe, re.IGNORECASE)
            for probe in probes
        )
        if structured:
            probes.extend(
                clause
                for probe in tuple(probes)
                for clause in re.split(r"\b(?:and|or)\b", probe, flags=re.IGNORECASE)
            )
        for probe in dict.fromkeys(probe.strip(" ,.;") for probe in probes if probe.strip()):
            if re.search(r"\b(?:and|or)\b", probe, re.IGNORECASE):
                continue
            pattern = re.escape(probe.strip())
            pattern = re.sub(r"\\ ", r"\\s+", pattern)
            match = re.search(
                rf"(?<![\w+#]){pattern}(?![\w+#])",
                query,
                re.IGNORECASE,
            )
            if match:
                matches.append(match)
        if matches:
            match = (
                min(matches, key=lambda item: item.start())
                if has_boolean_clause
                else max(matches, key=lambda item: (item.end() - item.start(), -item.start()))
            )
            mentions.append((match.start(), match.end(), requirement))

    mentions.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    non_overlapping = []
    for mention in mentions:
        if non_overlapping and mention[0] < non_overlapping[-1][1]:
            continue
        non_overlapping.append(mention)

    for index, (start, end, requirement) in enumerate(non_overlapping):
        prefix = query[max(0, start - 32):start]
        if re.search(r"\b(?:not\s+only)\s*$", prefix, re.IGNORECASE):
            continue
        if re.search(r"\b(?:not|without|excluding|except)\s*$", prefix, re.IGNORECASE):
            requirement.negated = True

        if index == 0:
            continue
        previous_start, previous_end, previous = non_overlapping[index - 1]
        connector = query[previous_end:start]
        if re.search(r"\b(?:not\s+only)\b", connector, re.IGNORECASE):
            continue
        if re.search(r"\b(?:and\s+)?(?:but\s+)?(?:not|without|excluding|except)\b", connector, re.IGNORECASE):
            requirement.negated = True
            if not re.search(r"\bor\b", connector, re.IGNORECASE):
                continue

        if not re.search(r"\bor\b", connector, re.IGNORECASE):
            continue

        group_id = (
            previous.group_id
            if previous.relationship.upper() == "OR" and previous.group_id
            else f"explicit_or_{previous.id}"
        )
        previous.group_id = group_id
        previous.relationship = "OR"
        requirement.group_id = group_id
        requirement.relationship = "OR"


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
