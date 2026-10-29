import re

from app.search.parser import parse_query
from app.search.classifier import classify_query
from app.search.requirements import normalize_requirement_graph
from app.search.normalization import (
    canonical_term,
    ensure_semantic_family_requirements,
    normalize_explicit_semantic_or,
    normalize_phrase,
    parse_explicit_experience_bounds,
)
from app.search.schema import (
    RoutingPacket,
    SearchRequirement,
    SearchSpecification,
)


def build_routing_packet(query: str) -> RoutingPacket:
    """
    Convert a recruiter query into a complete routing packet.

    Flow:

        Natural language query
                ↓
        Query parsing
                ↓
        Canonical specification
                ↓
        Route classification
                ↓
        RoutingPacket
    """

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    query = query.strip()

    # ---------------------------------------------------------
    # 1. Parse recruiter query
    # ---------------------------------------------------------

    parsed_query = parse_query(query)
    family_assumptions = ensure_semantic_family_requirements(query, parsed_query)

    # Preserve the recruiter’s actual activity wording when the query is
    # phrased as “candidates who have <activity>”. This avoids parser entity
    # substitutions such as changing “built products” into “built candidates”.
    activity_clause = re.search(
        r"\b(?:who|that)\s+(?:(?:has|have|had|is|are|was|were)\s+)?"
        r"(?P<activity>(?:built|builds?|developed|develops?|created|creates?|"
        r"designed|designs?|implemented|implements?|integrated|integrates?|"
        r"managed|manages?|led|leads?)\b.+?)\s*[?.!]*$",
        query,
        re.IGNORECASE,
    )
    if activity_clause and parsed_query.semantic_requirements:
        preserved_activity = " ".join(activity_clause.group("activity").split())
        parsed_query.semantic_requirements[0] = preserved_activity
        semantic_nodes = [
            item for item in parsed_query.requirements
            if item.type == "SEMANTIC"
            or "semantic_evidence_retrieval" in item.capabilities
        ]
        if semantic_nodes:
            semantic_nodes[0].original_text = preserved_activity
            semantic_nodes[0].normalized_text = preserved_activity.casefold()
            semantic_nodes[0].value = preserved_activity

    relevant_experience_match = re.search(
        r"\b(?P<years>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s*"
        r"(?:of\s+)?experience\s+(?:(?:in|with|on)\s+(?P<activity_preposition>.+?)|"
        r"(?P<activity_verb>(?:build\w*|develop\w*|work\w*|creat\w*|design\w*|"
        r"implement\w*|integrat\w*|manag\w*|deliver\w*|lead\w*|architect\w*)\b.+?))"
        r"(?=\s+and\s+(?:(?:who|that)\s+)?(?:know\w*|has|have|works?|builds?|"
        r"develops?|uses?|is|are|was|were)\b|\s*[?.!]*$)",
        query,
        re.IGNORECASE,
    )
    relevant_experience_months = None
    relevant_activity = None
    if relevant_experience_match:
        relevant_experience_months = round(
            float(relevant_experience_match.group("years")) * 12
        )
        relevant_activity = (
            relevant_experience_match.group("activity_preposition")
            or relevant_experience_match.group("activity_verb")
        ).strip()
        parsed_query.min_experience_years = None
        parsed_query.max_experience_years = None
        parsed_query.semantic_requirements = [relevant_activity]

        # The LLM can mistake a duration for a recency window or overall
        # experience. Replace those graph nodes with a scoped semantic tenure.
        has_explicit_recency = bool(re.search(
            r"\b(recent(?:ly)?|last|past|within|currently|current|ongoing)\b",
            query,
            re.IGNORECASE,
        ))
        removed_ids = {
            item.id for item in parsed_query.requirements
            if item.type == "TEMPORAL"
            and (
                not has_explicit_recency
                or re.search(r"\d+(?:\.\d+)?\s*(?:years?|yrs?).*experience", item.original_text, re.IGNORECASE)
            )
        }
        parsed_query.requirements = [
            item for item in parsed_query.requirements
            if item.id not in removed_ids
            and not (
                (item.field or "").casefold() in {"experience", "total_experience", "min_experience_years", "max_experience_years"}
            )
        ]
        rewritten_semantic_ids = set()
        semantic_nodes = [
            item for item in parsed_query.requirements
            if item.type.upper() == "SEMANTIC"
            or "semantic_evidence_retrieval" in item.capabilities
        ]
        activity_key = normalize_phrase(relevant_activity)
        for semantic_node in semantic_nodes:
            node_text = str(semantic_node.value or semantic_node.original_text)
            node_key = normalize_phrase(node_text)
            if node_key.startswith(activity_key) and re.search(
                r"\band\s+(?:(?:who|that)\s+)?(?:know\w*|has|have|works?|uses?)\b",
                node_text,
                re.IGNORECASE,
            ):
                semantic_node.original_text = relevant_activity
                semantic_node.normalized_text = activity_key
                semantic_node.value = relevant_activity
                rewritten_semantic_ids.add(semantic_node.id)
        if rewritten_semantic_ids:
            seen_semantic_text = set()
            duplicate_ids = {}
            deduped_requirements = []
            for requirement in parsed_query.requirements:
                if not (
                    requirement.type.upper() == "SEMANTIC"
                    or "semantic_evidence_retrieval" in requirement.capabilities
                ):
                    deduped_requirements.append(requirement)
                    continue
                semantic_key = normalize_phrase(str(requirement.value or requirement.original_text))
                if semantic_key not in seen_semantic_text:
                    seen_semantic_text.add(semantic_key)
                    deduped_requirements.append(requirement)
                else:
                    canonical_id = next(
                        item.id for item in deduped_requirements
                        if (item.type.upper() == "SEMANTIC"
                            or "semantic_evidence_retrieval" in item.capabilities)
                        and normalize_phrase(str(item.value or item.original_text)) == semantic_key
                    )
                    duplicate_ids[requirement.id] = canonical_id
            parsed_query.requirements = deduped_requirements
            if duplicate_ids:
                for requirement in parsed_query.requirements:
                    requirement.dependencies = list(dict.fromkeys(
                        duplicate_ids.get(item, item) for item in requirement.dependencies
                    ))
                    requirement.related_requirements = list(dict.fromkeys(
                        duplicate_ids.get(item, item) for item in requirement.related_requirements
                    ))
        for item in parsed_query.requirements:
            item.dependencies = [dependency for dependency in item.dependencies if dependency not in removed_ids]
            item.related_requirements = [related for related in item.related_requirements if related not in removed_ids]

    explicit_bounds = (
        None if relevant_experience_match else parse_explicit_experience_bounds(query)
    )
    if explicit_bounds is not None:
        parsed_query.min_experience_years = explicit_bounds["min_experience_years"]
        parsed_query.max_experience_years = explicit_bounds["max_experience_years"]
        experience_fields = {
            "experience", "total_experience", "min_experience_years",
            "max_experience_years",
        }
        removed_ids = {
            item.id for item in parsed_query.requirements
            if (item.field or "").casefold() in experience_fields
        }
        parsed_query.requirements = [
            item for item in parsed_query.requirements if item.id not in removed_ids
        ]
        if removed_ids:
            for item in parsed_query.requirements:
                item.dependencies = [value for value in item.dependencies if value not in removed_ids]
                item.related_requirements = [value for value in item.related_requirements if value not in removed_ids]
        minimum = explicit_bounds["min_experience_years"]
        maximum = explicit_bounds["max_experience_years"]
        label = (
            f"{'more than ' if explicit_bounds['min_experience_exclusive'] else 'at least '}{minimum:g} years"
            if minimum is not None and maximum is None else
            f"{minimum:g}-{maximum:g} years" if minimum is not None and maximum is not None else
            f"up to {maximum:g} years"
        )
        parsed_query.requirements.append(SearchRequirement(
            id="explicit_experience_bounds",
            original_text=label,
            normalized_text=label.casefold(),
            type="STRUCTURED",
            mandatory=True,
            source_of_truth="candidate_total_experience",
            capabilities=["structured_candidate_lookup"],
            field="experience",
            value={"min_experience_years": minimum, "max_experience_years": maximum},
            min_experience_exclusive=explicit_bounds["min_experience_exclusive"],
            confidence=1.0,
        ))

    # Seniority is useful title context but has no universal years mapping.
    # Keep the functional role filter, and disclose that no years threshold
    # was inferred from "senior" or similar wording.
    seniority_terms = ("senior", "junior", "mid-level", "mid level", "lead")
    lower_query = query.casefold()
    seniority_assumptions = [
        f"Seniority wording '{term}' was not converted to an experience-years filter."
        for term in seniority_terms
        if re.search(rf"\b{re.escape(term)}\b", lower_query)
    ]
    if seniority_assumptions:
        parsed_query.roles = [
            cleaned
            for role in parsed_query.roles
            if (cleaned := re.sub(
                r"^(?:(?:senior|junior|lead|mid[- ]level)\s+)+|(?:\s+(?:senior|junior|lead|mid[- ]level))+$",
                "",
                role,
                flags=re.IGNORECASE,
            ).strip())
        ]

    # A fresher convention is only applied when the recruiter did not state
    # an explicit range. Keep it visible as an inferred 0-1 year filter.
    is_fresher_query = any(
        term in lower_query
        for term in ("fresher", "freshers", "entry-level", "entry level", "recent graduate")
    )
    inferred_fresher_range = (
        is_fresher_query
        and parsed_query.min_experience_years is None
        and parsed_query.max_experience_years is None
    )
    assumptions = list(seniority_assumptions) + family_assumptions
    if relevant_experience_months is not None:
        assumptions.append(
            "Relevant experience counts dated roles with matching evidence; standalone project dates are not inferred."
        )
    if inferred_fresher_range:
        parsed_query.min_experience_years = 0
        parsed_query.max_experience_years = 1
        assumptions.append("'Fresher' is interpreted as 0-1 years of total experience.")
        parsed_query.roles = [
            cleaned
            for role in parsed_query.roles
            if (cleaned := re.sub(r"\b(?:freshers?|entry[- ]level|recent graduates?)\b", "", role, flags=re.IGNORECASE).strip())
        ]

    # ---------------------------------------------------------
    # 2. Classify retrieval route
    # ---------------------------------------------------------

    requirements = list(parsed_query.requirements)

    # Seniority is not a years threshold. Remove seniority adjectives from
    # role graph values too, since parsed graphs take precedence downstream.
    if seniority_assumptions or inferred_fresher_range:
        for requirement in requirements:
            if (requirement.field or "").casefold() not in {"role", "roles"}:
                continue
            if isinstance(requirement.value, str):
                cleaned = re.sub(
                    r"\b(?:senior|junior|lead|mid[- ]level|freshers?|entry[- ]level|recent graduates?)\b",
                    "",
                    requirement.value,
                    flags=re.IGNORECASE,
                )
                cleaned = " ".join(cleaned.split()).strip()
                if cleaned:
                    requirement.value = cleaned
                    requirement.normalized_text = cleaned.casefold()

    # Compatibility path for existing parser responses and tests. New parser
    # responses carry the graph directly; older responses are normalized into
    # the same graph here, without inspecting query phrases.
    def graph_covers(field_names: set[str], value, kind: str | None = None) -> bool:
        target = canonical_term(str(value), kind) if kind and value else normalize_phrase(str(value))
        for item in requirements:
            if (item.field or "").casefold() not in field_names:
                continue
            values = item.value if isinstance(item.value, list) else [item.value]
            for item_value in values:
                if not isinstance(item_value, str):
                    continue
                actual = canonical_term(item_value, kind) if kind else normalize_phrase(item_value)
                if actual == target:
                    return True
        return False

    for index, skill in enumerate(parsed_query.skills):
        if graph_covers({"skill", "skills"}, skill, "skill"):
            continue
        requirements.append(SearchRequirement(
            id=f"structured_skill_{index + 1}",
            original_text=skill,
            normalized_text=" ".join(skill.casefold().split()),
            type="STRUCTURED",
            source_of_truth="candidate_skill",
            capabilities=["structured_candidate_lookup"],
            field="skills",
            value=skill,
        ))
    for index, role in enumerate(parsed_query.roles):
        if graph_covers({"role", "roles"}, role, "role"):
            continue
        requirements.append(SearchRequirement(
            id=f"structured_role_{index + 1}",
            original_text=role,
            normalized_text=" ".join(role.casefold().split()),
            type="STRUCTURED",
            source_of_truth="experience_role",
            capabilities=["structured_experience_lookup"],
            field="roles",
            value=role,
        ))
    for index, company in enumerate(parsed_query.companies):
        if graph_covers({"company", "companies"}, company):
            continue
        requirements.append(SearchRequirement(
            id=f"structured_company_{index + 1}",
            original_text=company,
            normalized_text=" ".join(company.casefold().split()),
            type="STRUCTURED",
            source_of_truth="experience_company",
            capabilities=["structured_experience_lookup"],
            field="companies",
            value=company,
        ))
    if parsed_query.location and not graph_covers({"location"}, parsed_query.location):
        requirements.append(SearchRequirement(
            id="structured_location",
            original_text=parsed_query.location,
            normalized_text=" ".join(parsed_query.location.casefold().split()),
            type="STRUCTURED",
            source_of_truth="candidate_location",
            capabilities=["structured_candidate_lookup"],
            field="location",
            value=parsed_query.location,
        ))
    if (
        parsed_query.min_experience_years is not None
        or parsed_query.max_experience_years is not None
    ) and not any(
        (requirement.field or "").casefold()
        in {"experience", "total_experience", "min_experience_years", "max_experience_years"}
        for requirement in requirements
    ):
        label = f"{parsed_query.min_experience_years or 0}..{parsed_query.max_experience_years or 'open'} years experience"
        requirements.append(SearchRequirement(
            id="structured_experience",
            original_text=label,
            normalized_text=label.casefold(),
            type="STRUCTURED",
            source_of_truth="candidate_total_experience",
            capabilities=["structured_candidate_lookup"],
            field="experience",
            value={
                "min_experience_years": parsed_query.min_experience_years,
                "max_experience_years": parsed_query.max_experience_years,
            },
        ))
    for index, semantic in enumerate(parsed_query.semantic_requirements):
        semantic_tokens = set(re.findall(r"[a-z0-9+#.]+", normalize_phrase(semantic)))
        represented = False
        for item in requirements:
            if ("semantic_evidence_retrieval" not in item.capabilities
                    and item.type.upper() != "SEMANTIC"):
                continue
            existing_tokens = set(re.findall(
                r"[a-z0-9+#.]+", normalize_phrase(str(item.value or item.normalized_text))
            ))
            denominator = min(len(semantic_tokens), len(existing_tokens))
            if denominator and len(semantic_tokens & existing_tokens) / denominator >= 0.8:
                represented = True
                break
        if not semantic or represented:
            continue
        requirements.append(SearchRequirement(
            id=f"semantic_{index + 1}",
            original_text=semantic,
            normalized_text=" ".join(semantic.casefold().split()),
            type="SEMANTIC",
            source_of_truth="resume_evidence",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
            field="semantic_requirements",
            value=semantic,
        ))

    if relevant_experience_months is not None and relevant_activity:
        semantic_nodes = [
            item for item in requirements
            if item.type == "SEMANTIC"
            or "semantic_evidence_retrieval" in item.capabilities
        ]
        if semantic_nodes:
            scoped_requirement = semantic_nodes[0]
            scoped_requirement.original_text = relevant_activity
            scoped_requirement.normalized_text = relevant_activity.casefold()
            scoped_requirement.value = relevant_activity
            # The user explicitly asked for this activity and duration. Do
            # not let an optional/OR semantic node qualify on some other
            # resume evidence while bypassing the requested activity.
            scoped_requirement.mandatory = True
            scoped_requirement.relationship = "AND"
            scoped_requirement.group_id = None
        else:
            scoped_requirement = SearchRequirement(
                id="scoped_semantic_experience",
                original_text=relevant_activity,
                normalized_text=relevant_activity.casefold(),
                type="SEMANTIC",
                mandatory=True,
                source_of_truth="resume_evidence",
                capabilities=["semantic_evidence_retrieval", "evidence_validation"],
                field="semantic_requirements",
                value=relevant_activity,
            )
            requirements.append(scoped_requirement)
        scoped_requirement.minimum_relevant_experience_months = relevant_experience_months

    if inferred_fresher_range:
        experience_requirements = [
            requirement for requirement in requirements
            if (requirement.field or "").casefold()
            in {"experience", "total_experience", "min_experience_years", "max_experience_years"}
        ]
        if experience_requirements:
            for requirement in experience_requirements:
                if requirement.field in {"experience", "total_experience"}:
                    requirement.value = {
                        "min_experience_years": 0,
                        "max_experience_years": 1,
                    }
                    requirement.normalized_text = "0-1 years total experience"
                    requirement.confidence = 0.75
                elif requirement.field == "min_experience_years":
                    requirement.value = 0
                elif requirement.field == "max_experience_years":
                    requirement.value = 1
        else:
            requirements.append(SearchRequirement(
                id="inferred_fresher_experience",
                original_text="fresher (inferred 0-1 years experience)",
                normalized_text="0-1 years total experience",
                type="STRUCTURED",
                mandatory=True,
                source_of_truth="candidate_total_experience",
                capabilities=["structured_candidate_lookup"],
                field="experience",
                value={"min_experience_years": 0, "max_experience_years": 1},
                confidence=0.75,
            ))

    parsed_query.semantic_requirements = normalize_explicit_semantic_or(
        query,
        requirements,
        parsed_query.semantic_requirements,
    )

    # Fill abstract capabilities for requirements supplied by an LLM that
    # omitted them; preserve all parsed fields and dependencies.
    requirements = normalize_requirement_graph(requirements, query=query)
    for requirement in requirements:
        if requirement.capabilities:
            continue
        defaults = {
            "STRUCTURED": ["structured_candidate_lookup"],
            "SEMANTIC": ["semantic_evidence_retrieval", "evidence_validation"],
            "TEMPORAL": ["temporal_validation", "evidence_validation"],
            "RELATIONAL": ["relationship_resolution", "evidence_validation"],
            "COMPOSITE": ["evidence_validation"],
        }
        requirement.capabilities = defaults.get(
            requirement.type, ["evidence_validation"]
        )

    parsed_query.requirements = requirements
    route = classify_query(parsed_query)

    graph_values: dict[str, list] = {
        "skills": [], "roles": [], "companies": [], "semantic_requirements": [],
    }
    graph_location = None
    graph_min_experience = None
    graph_max_experience = None
    for requirement in requirements:
        field = (requirement.field or "").casefold()
        value = requirement.value
        if field in {"skill", "skills", "role", "roles", "company", "companies"} and value:
            canonical = {"skill": "skills", "role": "roles", "company": "companies"}.get(field, field)
            graph_values[canonical].append(str(value))
        elif field == "location" and value:
            graph_location = str(value)
        elif field in {"experience", "total_experience"} and isinstance(value, dict):
            graph_min_experience = value.get("min_experience_years", graph_min_experience)
            graph_max_experience = value.get("max_experience_years", graph_max_experience)
        elif field == "min_experience_years" and value is not None:
            graph_min_experience = float(value)
        elif field == "max_experience_years" and value is not None:
            graph_max_experience = float(value)
        if "semantic_evidence_retrieval" in requirement.capabilities:
            semantic_value = value if isinstance(value, str) else requirement.normalized_text
            if semantic_value:
                graph_values["semantic_requirements"].append(str(semantic_value))

    # ---------------------------------------------------------
    # 3. Build canonical search specification
    # ---------------------------------------------------------

    specification = SearchSpecification(
        requested_count=parsed_query.requested_count,
        count_explicit=parsed_query.count_explicit,
        skills=graph_values["skills"] or parsed_query.skills,
        roles=graph_values["roles"] or parsed_query.roles,
        companies=parsed_query.companies or graph_values["companies"],
        location=parsed_query.location or graph_location,
        min_experience_years=parsed_query.min_experience_years if parsed_query.min_experience_years is not None else graph_min_experience,
        max_experience_years=parsed_query.max_experience_years if parsed_query.max_experience_years is not None else graph_max_experience,
        semantic_requirements=parsed_query.semantic_requirements or graph_values["semantic_requirements"],
        assumptions=assumptions,
        requirements=requirements,
        route=route,
    )

    # ---------------------------------------------------------
    # 4. Separate structured requirements
    # ---------------------------------------------------------

    structured_requirements = {
        "skills": specification.skills,
        "roles": specification.roles,
        "companies": specification.companies,
        "location": specification.location,
        "min_experience_years": (
            specification.min_experience_years
        ),
        "max_experience_years": (
            specification.max_experience_years
        ),
    }

    # ---------------------------------------------------------
    # 5. Build final routing packet
    # ---------------------------------------------------------

    return RoutingPacket(
        query=query,
        specification=specification,
        route=route,
        structured_requirements=structured_requirements,
        semantic_requirements=specification.semantic_requirements,
    )
