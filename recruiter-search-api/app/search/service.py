import re





from app.search.parser import parse_query

from app.search.classifier import classify_query

from app.search.requirements import normalize_requirement_graph

from app.search.normalization import (

    _FAMILY_QUERY_PATTERNS,

    apply_explicit_boolean_operators,

    canonical_term,

    equivalent_terms,

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





def build_routing_packet(
    query: str,
    manual_skills: list[str] | None = None,
) -> RoutingPacket:

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

    # Merge skills manually selected in the frontend into the parsed query.
    # Manual skills are recruiter-supplied structured requirements, so they
    # must participate in the same deterministic retrieval path as parsed skills.
    for skill in manual_skills or []:
        skill = skill.strip()
        if not skill:
            continue
        if not any(
            normalize_phrase(existing) == normalize_phrase(skill)
            for existing in parsed_query.skills
        ):
            parsed_query.skills.append(skill)


    family_assumptions = ensure_semantic_family_requirements(

        query,

        parsed_query,

    )



    explicit_skill = re.search(

        r"\bknows?\s+(?P<skill>[^,;.!?]+?)(?=\s+(?:and|or)\s+|\s\*$)",

        query,

        re.IGNORECASE,

    )



    if explicit_skill:

        skill = re.sub(

            r"\s+(?:framework|technology|technologies|language|tool|tools)$",

            "",

            " ".join(explicit_skill.group("skill").split()),

            flags=re.IGNORECASE,

        ).strip()



        is_broad_family = any(

            re.search(pattern, skill, re.IGNORECASE)

            for pattern in _FAMILY_QUERY_PATTERNS.values()

        )



        existing_skills = {

            normalize_phrase(value)

            for value in parsed_query.skills

        }



        existing_skills.update(

            normalize_phrase(str(item.value))

            for item in parsed_query.requirements

            if (item.field or "").casefold() in {"skill", "skills"}

            and isinstance(item.value, str)

        )



        if (

            skill

            and not is_broad_family

            and normalize_phrase(skill) not in existing_skills

        ):

            parsed_query.skills.append(skill)



            parsed_query.requirements.append(

                SearchRequirement(

                    id="explicit_known_skill",

                    original_text=skill,

                    normalized_text=normalize_phrase(skill),

                    type="STRUCTURED",

                    mandatory=True,

                    source_of_truth="candidate_skills",

                    capabilities=["structured_candidate_lookup"],

                    field="skill",

                    value=skill,

                    canonical_value=canonical_term(skill, "skill"),

                    confidence=0.9,

                )

            )



    # ---------------------------------------------------------

    # Preserve recruiter activity wording

    # ---------------------------------------------------------



    activity_clause = re.search(

        r"\b(?:who|that)\s+(?:(?:has|have|had|is|are|was|were)\s+)?"

        r"(?P<activity>(?:built|builds?|developed|develops?|created|creates?|"

        r"designed|designs?|implemented|implements?|integrated|integrates?|"

        r"managed|manages?|led|leads?)\b.+?)"

        r"(?=\s+and\s+(?:(?:who|that)\s+)?"

        r"(?:(?:has|have|had|is|are|was|were)\s+)?"

        r"(?:built|builds?|developed|develops?|created|creates?|designed|"

        r"designs?|implemented|implements?|integrated|integrates?|worked|"

        r"works?|used|uses?|knows?|managed|manages?|led|leads?)\b|"

        r"\s\*$)",

        query,

        re.IGNORECASE,

    )



    semantic_nodes = [

        item

        for item in parsed_query.requirements

        if item.type == "SEMANTIC"

        or "semantic_evidence_retrieval" in item.capabilities

    ]



    if activity_clause and (

        parsed_query.semantic_requirements or semantic_nodes

    ):

        preserved_activity = " ".join(

            activity_clause.group("activity").split()

        )



        if parsed_query.semantic_requirements:

            parsed_query.semantic_requirements[0] = preserved_activity

        else:

            parsed_query.semantic_requirements.append(

                preserved_activity

            )



        if semantic_nodes:

            semantic_nodes[0].original_text = preserved_activity

            semantic_nodes[0].normalized_text = preserved_activity.casefold()

            semantic_nodes[0].value = preserved_activity



    # ---------------------------------------------------------

    # Relevant experience

    # ---------------------------------------------------------



    relevant_experience_match = re.search(

        r"\b(?P<years>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s*"

        r"(?:of\s+)?experience\s+(?:(?:in|with|on)\s+(?P<activity_preposition>.+?)|"

        r"(?P<activity_verb>(?:build\w*|develop\w*|work\w*|creat\w*|design\w*|"
        r"implement\w\*|integrat\w\*|manag\w\*|deliver\w\*|lead\w\*|architect\w\*)\b.+?))"

        r"(?=\s+and\s+(?:(?:who|that)\s+)?(?:know\w\*|has|have|works?|builds?|"

        r"develops?|uses?|is|are|was|were)\b|\s\*$)",

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



        has_explicit_recency = bool(

            re.search(

                r"\b(recent(?:ly)?|last|past|within|currently|current|ongoing)\b",

                query,

                re.IGNORECASE,

            )

        )



        removed_ids = {

            item.id

            for item in parsed_query.requirements

            if item.type == "TEMPORAL"

            and (

                not has_explicit_recency

                or re.search(

                    r"\d+(?:**\\.**\d+)?\s\*(?:years?|yrs?).\*experience",

                    item.original_text,

                    re.IGNORECASE,

                )

            )

        }



        parsed_query.requirements = [

            item

            for item in parsed_query.requirements

            if item.id not in removed_ids

            and not (

                (item.field or "").casefold()

                in {

                    "experience",

                    "total_experience",

                    "min_experience_years",

                    "max_experience_years",

                }

            )

        ]



        rewritten_semantic_ids = set()



        semantic_nodes = [

            item

            for item in parsed_query.requirements

            if item.type.upper() == "SEMANTIC"

            or "semantic_evidence_retrieval" in item.capabilities

        ]



        activity_key = normalize_phrase(relevant_activity)



        for semantic_node in semantic_nodes:

            node_text = str(

                semantic_node.value

                or semantic_node.original_text

            )



            node_key = normalize_phrase(node_text)



            if node_key.startswith(activity_key) and re.search(

                r"\band\s+(?:(?:who|that)\s+)?(?:know\w\*|has|have|works?|uses?)\b",

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

                    or "semantic_evidence_retrieval"

                    in requirement.capabilities

                ):

                    deduped_requirements.append(requirement)

                    continue



                semantic_key = normalize_phrase(

                    str(

                        requirement.value

                        or requirement.original_text

                    )

                )



                if semantic_key not in seen_semantic_text:

                    seen_semantic_text.add(semantic_key)

                    deduped_requirements.append(requirement)

                else:

                    canonical_id = next(

                        item.id

                        for item in deduped_requirements

                        if (

                            item.type.upper() == "SEMANTIC"

                            or "semantic_evidence_retrieval"

                            in item.capabilities

                        )

                        and normalize_phrase(

                            str(

                                item.value

                                or item.original_text

                            )

                        ) == semantic_key

                    )



                    duplicate_ids[requirement.id] = canonical_id



            parsed_query.requirements = deduped_requirements



            if duplicate_ids:

                for requirement in parsed_query.requirements:

                    requirement.dependencies = list(

                        dict.fromkeys(

                            duplicate_ids.get(

                                item,

                                item,

                            )

                            for item in requirement.dependencies

                        )

                    )



                    requirement.related_requirements = list(

                        dict.fromkeys(

                            duplicate_ids.get(

                                item,

                                item,

                            )

                            for item in requirement.related_requirements

                        )

                    )



        for item in parsed_query.requirements:

            item.dependencies = [

                dependency

                for dependency in item.dependencies

                if dependency not in removed_ids

            ]



            item.related_requirements = [

                related

                for related in item.related_requirements

                if related not in removed_ids

            ]



    explicit_bounds = (

        None

        if relevant_experience_match

        else parse_explicit_experience_bounds(query)

    )



    if explicit_bounds is not None:

        parsed_query.min_experience_years = (

            explicit_bounds["min_experience_years"]

        )



        parsed_query.max_experience_years = (

            explicit_bounds["max_experience_years"]

        )



        experience_fields = {

            "experience",

            "total_experience",

            "min_experience_years",

            "max_experience_years",

        }



        removed_ids = {

            item.id

            for item in parsed_query.requirements

            if (item.field or "").casefold()

            in experience_fields

        }



        parsed_query.requirements = [

            item

            for item in parsed_query.requirements

            if item.id not in removed_ids

        ]



        if removed_ids:

            for item in parsed_query.requirements:

                item.dependencies = [

                    value

                    for value in item.dependencies

                    if value not in removed_ids

                ]



                item.related_requirements = [

                    value

                    for value in item.related_requirements

                    if value not in removed_ids

                ]



        minimum = explicit_bounds["min_experience_years"]

        maximum = explicit_bounds["max_experience_years"]



        label = (

            f"{'more than ' if explicit_bounds['min_experience_exclusive'] else 'at least '}"

            f"{minimum:g} years"

            if minimum is not None and maximum is None

            else (

                f"{minimum:g}-{maximum:g} years"

                if minimum is not None and maximum is not None

                else f"up to {maximum:g} years"

            )

        )



        parsed_query.requirements.append(

            SearchRequirement(

                id="explicit_experience_bounds",

                original_text=label,

                normalized_text=label.casefold(),

                type="STRUCTURED",

                mandatory=True,

                source_of_truth="candidate_total_experience",

                capabilities=["structured_candidate_lookup"],

                field="experience",

                value={

                    "min_experience_years": minimum,

                    "max_experience_years": maximum,

                },

                min_experience_exclusive=(

                    explicit_bounds["min_experience_exclusive"]

                ),

                confidence=1.0,

            )

        )



    # ---------------------------------------------------------

    # Seniority

    # ---------------------------------------------------------



    seniority_terms = (

        "senior",

        "junior",

        "mid-level",

        "mid level",

        "lead",

    )



    lower_query = query.casefold()



    seniority_assumptions = [

        f"Seniority wording '{term}' was not converted to an experience-years filter."

        for term in seniority_terms

        if re.search(

            rf"\b{re.escape(term)}\b",

            lower_query,

        )

    ]



    if seniority_assumptions:

        parsed_query.roles = [

            cleaned

            for role in parsed_query.roles

            if (

                cleaned := re.sub(

                    r"^(?:(?:senior|junior|lead|mid[- ]level)\s+)+|"

                    r"(?:\s+(?:senior|junior|lead|mid[- ]level))+$",

                    "",

                    role,

                    flags=re.IGNORECASE,

                ).strip()

            )

        ]



    # ---------------------------------------------------------

    # Fresher

    # ---------------------------------------------------------



    fresher_terms = (
    "fresher",
    "freshers",
    "entry-level",
    "entry level",
    "recent graduate",
    )

    is_fresher_query = any(
        term in lower_query
        for term in fresher_terms
    )

    is_negated_fresher_query = any(
        re.search(
            rf"\bnot\s+(?:a\s+)?{re.escape(term)}\b",
            lower_query,
        )
        for term in fresher_terms
    )



    inferred_fresher_range = (
    is_fresher_query
    and not is_negated_fresher_query
    and parsed_query.min_experience_years is None
    and parsed_query.max_experience_years is None
)



    assumptions = list(seniority_assumptions) + family_assumptions



    if relevant_experience_months is not None:

        assumptions.append(

            "Relevant experience counts dated roles with matching evidence; "

            "standalone project dates are not inferred."

        )



    if inferred_fresher_range:

        parsed_query.min_experience_years = 0

        parsed_query.max_experience_years = 1



        assumptions.append(

            "'Fresher' is interpreted as 0-1 years of total experience."

        )



        parsed_query.roles = [

            cleaned

            for role in parsed_query.roles

            if (

                cleaned := re.sub(

                    r"\b(?:freshers?|entry[- ]level|recent graduates?)\b",

                    "",

                    role,

                    flags=re.IGNORECASE,

                ).strip()

            )

        ]



    # ---------------------------------------------------------

    # 2. Build requirements

    # ---------------------------------------------------------



    requirements = list(parsed_query.requirements)

    negated_fresher_range = False

    if (
        is_negated_fresher_query
        and parsed_query.min_experience_years is None
        and parsed_query.max_experience_years is None
    ):
        parsed_query.min_experience_years = 0
        parsed_query.max_experience_years = 1
        negated_fresher_range = True
    



    if seniority_assumptions or inferred_fresher_range or negated_fresher_range:

        for requirement in requirements:

            if (requirement.field or "").casefold() not in {

                "role",

                "roles",

            }:

                continue



            if isinstance(requirement.value, str):

                cleaned = re.sub(

                    r"\b(?:senior|junior|lead|mid[- ]level|freshers?|"

                    r"entry[- ]level|recent graduates?)\b",

                    "",

                    requirement.value,

                    flags=re.IGNORECASE,

                )



                cleaned = " ".join(cleaned.split()).strip()



                if cleaned:

                    requirement.value = cleaned

                    requirement.normalized_text = cleaned.casefold()



    # Compatibility path for parser responses and tests.

    def graph_covers(

        field_names: set[str],

        value,

        kind: str | None = None,

    ) -> bool:

        target = (

            canonical_term(str(value), kind)

            if kind and value

            else normalize_phrase(str(value))

        )



        for item in requirements:

            if (item.field or "").casefold() not in field_names:

                continue



            values = (

                item.value

                if isinstance(item.value, list)

                else [item.value]

            )



            for item_value in values:

                if not isinstance(item_value, str):

                    continue



                actual = (

                    canonical_term(item_value, kind)

                    if kind

                    else normalize_phrase(item_value)

                )



                if actual == target:

                    return True



        return False



    for index, skill in enumerate(parsed_query.skills):

        if graph_covers(

            {"skill", "skills"},

            skill,

            "skill",

        ):

            continue



        requirements.append(

            SearchRequirement(

                id=f"structured_skill_{index + 1}",

                original_text=skill,

                normalized_text=" ".join(

                    skill.casefold().split()

                ),

                type="STRUCTURED",

                source_of_truth="candidate_skill",

                capabilities=["structured_candidate_lookup"],

                field="skills",

                value=skill,

            )

        )



    for index, role in enumerate(parsed_query.roles):

        if graph_covers(

            {"role", "roles"},

            role,

            "role",

        ):

            continue



        requirements.append(

            SearchRequirement(

                id=f"structured_role_{index + 1}",

                original_text=role,

                normalized_text=" ".join(

                    role.casefold().split()

                ),

                type="STRUCTURED",

                source_of_truth="experience_role",

                capabilities=["structured_experience_lookup"],

                field="roles",

                value=role,

            )

        )



    for index, company in enumerate(parsed_query.companies):

        if graph_covers(

            {"company", "companies"},

            company,

        ):

            continue


        requirements.append(

            SearchRequirement(

                id=f"structured_company_{index + 1}",

                original_text=company,

                normalized_text=" ".join(

                    company.casefold().split()

                ),

                type="STRUCTURED",

                source_of_truth="experience_company",

                capabilities=["structured_experience_lookup"],

                field="companies",

                value=company,

            )

        )



    # ---------------------------------------------------------

    # LOCATION

    # ---------------------------------------------------------

    #

    # IMPORTANT:

    # Preserve the parser's location_scope.

    #

    # CANDIDATE:

    #     candidate.location must match

    #

    # EXPERIENCE:

    #     relevant experience.location must match

    #

    # Do NOT default every location to candidate_location.

    # ---------------------------------------------------------



    if parsed_query.location and not graph_covers(

        {"location"},

        parsed_query.location,

    ):

        location_source_of_truth = (

            "experience_location"

            if parsed_query.location_scope == "EXPERIENCE"

            else "candidate_location"

        )



        location_capability = (

            ["structured_experience_lookup"]

            if parsed_query.location_scope == "EXPERIENCE"

            else ["structured_candidate_lookup"]

        )



        requirements.append(

            SearchRequirement(

                id="structured_location",

                original_text=parsed_query.location,

                normalized_text=" ".join(

                    parsed_query.location.casefold().split()

                ),

                type="STRUCTURED",

                source_of_truth=location_source_of_truth,

                capabilities=location_capability,

                field="location",

                value=parsed_query.location,

                location_scope=parsed_query.location_scope,

            )

        )



    # ---------------------------------------------------------

    # TOTAL EXPERIENCE

    # ---------------------------------------------------------



    if (

        parsed_query.min_experience_years is not None

        or parsed_query.max_experience_years is not None

    ) and not any(

        (requirement.field or "").casefold()

        in {

            "experience",

            "total_experience",

            "min_experience_years",

            "max_experience_years",

        }

        for requirement in requirements

    ):

        label = (

            f"{parsed_query.min_experience_years or 0}.."

            f"{parsed_query.max_experience_years or 'open'} years experience"

        )



        requirements.append(
            SearchRequirement(
                id="structured_experience",
                original_text=label,
                normalized_text=label.casefold(),
                type="STRUCTURED",
                source_of_truth="candidate_total_experience",
                capabilities=["structured_candidate_lookup"],
                field="experience",
                value={
                    "min_experience_years": (
                        parsed_query.min_experience_years
                    ),
                    "max_experience_years": (
                        parsed_query.max_experience_years
                    ),
                },
                negated=negated_fresher_range,
            )
        )



    # ---------------------------------------------------------

    # Semantic requirements

    # ---------------------------------------------------------



    for index, semantic in enumerate(

        parsed_query.semantic_requirements

    ):

        semantic_tokens = set(

            re.findall(

                r"[a-z0-9+#.]+",

                normalize_phrase(semantic),

            )

        )



        represented = False



        for item in requirements:

            if (

                "semantic_evidence_retrieval"

                not in item.capabilities

                and item.type.upper() != "SEMANTIC"

            ):

                continue



            existing_tokens = set(

                re.findall(

                    r"[a-z0-9+#.]+",

                    normalize_phrase(

                        str(

                            item.value

                            or item.normalized_text

                        )

                    ),

                )

            )



            denominator = min(

                len(semantic_tokens),

                len(existing_tokens),

            )



            if (

                denominator

                and len(

                    semantic_tokens & existing_tokens

                )

                / denominator

                >= 0.8

            ):

                represented = True

                break



        if not semantic or represented:

            continue



        requirements.append(

            SearchRequirement(

                id=f"semantic_{index + 1}",

                original_text=semantic,

                normalized_text=" ".join(

                    semantic.casefold().split()

                ),

                type="SEMANTIC",

                source_of_truth="resume_evidence",

                capabilities=[

                    "semantic_evidence_retrieval",

                    "evidence_validation",

                ],

                field="semantic_requirements",

                value=semantic,

            )

        )



    # ---------------------------------------------------------

    # Relevant experience scoped to semantic requirement

    # ---------------------------------------------------------



    if (

        relevant_experience_months is not None

        and relevant_activity

    ):

        semantic_nodes = [

            item

            for item in requirements

            if item.type == "SEMANTIC"

            or "semantic_evidence_retrieval"

            in item.capabilities

        ]



        if semantic_nodes:

            scoped_requirement = semantic_nodes[0]



            scoped_requirement.original_text = relevant_activity

            scoped_requirement.normalized_text = (

                relevant_activity.casefold()

            )

            scoped_requirement.value = relevant_activity

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

                capabilities=[

                    "semantic_evidence_retrieval",

                    "evidence_validation",

                ],

                field="semantic_requirements",

                value=relevant_activity,

            )



            requirements.append(scoped_requirement)



        scoped_requirement.minimum_relevant_experience_months = (

            relevant_experience_months

        )



    # ---------------------------------------------------------

    # Fresher range

    # ---------------------------------------------------------



    if inferred_fresher_range:

        experience_requirements = [

            requirement

            for requirement in requirements

            if (requirement.field or "").casefold()

            in {

                "experience",

                "total_experience",

                "min_experience_years",

                "max_experience_years",

            }

        ]



        if experience_requirements:

            for requirement in experience_requirements:

                if requirement.field in {

                    "experience",

                    "total_experience",

                }:

                    requirement.value = {

                        "min_experience_years": 0,

                        "max_experience_years": 1,

                    }



                    requirement.normalized_text = (

                        "0-1 years total experience"

                    )



                    requirement.confidence = 0.75



                elif requirement.field == "min_experience_years":

                    requirement.value = 0



                elif requirement.field == "max_experience_years":

                    requirement.value = 1



        else:

            requirements.append(

                SearchRequirement(

                    id="inferred_fresher_experience",

                    original_text=(

                        "fresher (inferred 0-1 years experience)"

                    ),

                    normalized_text=(

                        "0-1 years total experience"

                    ),

                    type="STRUCTURED",

                    mandatory=True,

                    source_of_truth="candidate_total_experience",

                    capabilities=["structured_candidate_lookup"],

                    field="experience",

                    value={

                        "min_experience_years": 0,

                        "max_experience_years": 1,

                    },

                    confidence=0.75,

                )

            )



    # ---------------------------------------------------------

    # Normalize skills / boolean logic

    # ---------------------------------------------------------



    _normalize_compound_structured_skills(

        parsed_query.skills,

        requirements,

    )



    _deduplicate_structured_skill_requirements(

        requirements,

    )



    _normalize_explicit_structured_skill_or(

        query,

        requirements,

    )



    parsed_query.semantic_requirements = (

        normalize_explicit_semantic_or(

            query,

            requirements,

            parsed_query.semantic_requirements,

        )

    )



    apply_explicit_boolean_operators(

        query,

        requirements,

    )



    # ---------------------------------------------------------

    # Normalize requirement graph

    # ---------------------------------------------------------



    requirements = normalize_requirement_graph(

        requirements,

        query=query,

    )



    # ---------------------------------------------------------

    # Preserve structured equivalents

    # ---------------------------------------------------------



    _ensure_structured_equivalents(requirements)



    # ---------------------------------------------------------

    # Same-experience relationships

    # ---------------------------------------------------------



    _apply_same_experience_relationships(

        query,

        requirements,

    )



    # ---------------------------------------------------------

    # Fill missing capabilities

    # ---------------------------------------------------------



    for requirement in requirements:

        if requirement.capabilities:

            continue



        defaults = {

            "STRUCTURED": [

                "structured_candidate_lookup"

            ],

            "SEMANTIC": [

                "semantic_evidence_retrieval",

                "evidence_validation",

            ],

            "TEMPORAL": [

                "temporal_validation",

                "evidence_validation",

            ],

            "RELATIONAL": [

                "relationship_resolution",

                "evidence_validation",

            ],

            "COMPOSITE": [

                "evidence_validation"

            ],

        }



        requirement.capabilities = defaults.get(

            requirement.type,

            ["evidence_validation"],

        )



    parsed_query.requirements = requirements



    # ---------------------------------------------------------

    # Classify route

    # ---------------------------------------------------------



    route = classify_query(parsed_query)



    # ---------------------------------------------------------

    # Build graph values

    # ---------------------------------------------------------



    graph_values: dict[str, list] = {
    "skills": [],
    "negated_skills": [],
    "roles": [],
    "negated_roles": [],
    "companies": [],
    "negated_companies": [],
    "semantic_requirements": [],
}



    graph_location = None
    graph_location_scope = None
    graph_location_negated = False

    graph_min_experience = None
    graph_max_experience = None
    graph_experience_negated = False
    graph_min_experience_exclusive = False



    for requirement in requirements:
        field = (

            requirement.field or ""

        ).casefold()



        value = requirement.value



        if (

            field

            in {

                "skill",

                "skills",

                "role",

                "roles",

                "company",

                "companies",

            }

            and value

        ):

            canonical = {

                "skill": "skills",

                "role": "roles",

                "company": "companies",

            }.get(

                field,

                field,

            )



            target = f"negated_{canonical}" if requirement.negated else canonical
            graph_values[target].append(str(value))



        elif field == "location" and value:
            graph_location = str(value)

            # Preserve whether the location refers to the
            # candidate or employment record.
            graph_location_scope = (
                requirement.location_scope
            )

            # Preserve explicit NOT semantics.
            graph_location_negated = requirement.negated



        elif (
                field in {
                    "experience",
                    "total_experience",
                }
                and isinstance(value, dict)
            ):
                graph_min_experience = value.get(
                    "min_experience_years",
                    graph_min_experience,
                )

                graph_max_experience = value.get(
                    "max_experience_years",
                    graph_max_experience,
                )

                graph_experience_negated = requirement.negated
                graph_min_experience_exclusive = (
                    requirement.min_experience_exclusive
                )



        elif (
                field == "min_experience_years"
                and value is not None
            ):
                graph_min_experience = float(value)
                graph_experience_negated = requirement.negated
                graph_min_experience_exclusive = (
                    requirement.min_experience_exclusive
                )

        elif (
                field == "max_experience_years"
                and value is not None
            ):
            graph_max_experience = float(value)
            graph_experience_negated = requirement.negated



        if (

            "semantic_evidence_retrieval"

            in requirement.capabilities

        ):

            semantic_value = (

                value

                if isinstance(value, str)

                else requirement.normalized_text

            )



            if semantic_value:

                graph_values[

                    "semantic_requirements"

                ].append(

                    str(semantic_value)

                )



    # ---------------------------------------------------------

    # 3. Build canonical search specification

    # ---------------------------------------------------------



    specification = SearchSpecification(

        requested_count=parsed_query.requested_count,

        count_explicit=parsed_query.count_explicit,

        skills=(

            graph_values["skills"]

            or parsed_query.skills

        ),

        roles=(

            graph_values["roles"]

            or parsed_query.roles

        ),

        companies=(

            parsed_query.companies

            or graph_values["companies"]

        ),

        location=(

            parsed_query.location

            or graph_location

        ),

        location_scope=(

            parsed_query.location_scope

            or graph_location_scope

        ),

        min_experience_years=(

            parsed_query.min_experience_years

            if parsed_query.min_experience_years

            is not None

            else graph_min_experience

        ),

        max_experience_years=(

            parsed_query.max_experience_years

            if parsed_query.max_experience_years

            is not None

            else graph_max_experience

        ),

        semantic_requirements=(

            parsed_query.semantic_requirements

            or graph_values["semantic_requirements"]

        ),

        assumptions=assumptions,

        requirements=requirements,

        route=route,

    )



    # ---------------------------------------------------------

    # 4. Separate structured requirements

    # ---------------------------------------------------------



    structured_requirements = {
    "skills": graph_values.get("skills", []),
    "negated_skills": graph_values.get(
        "negated_skills",
        [],
    ),
    "roles": specification.roles,
    "negated_roles": graph_values.get(
        "negated_roles",
        [],
    ),
    "companies": specification.companies,
    "negated_companies": graph_values.get(
        "negated_companies",
        [],
    ),
    "location": specification.location,
    "location_scope": specification.location_scope,
    "location_negated": graph_location_negated,
    "min_experience_years": specification.min_experience_years,
    "max_experience_years": specification.max_experience_years,
    "experience_negated": graph_experience_negated,
    "min_experience_exclusive": graph_min_experience_exclusive,
}


    # ---------------------------------------------------------

    # 5. Build final routing packet

    # ---------------------------------------------------------



    return RoutingPacket(

        query=query,

        specification=specification,

        route=route,

        structured_requirements=structured_requirements,

        semantic_requirements=(

            specification.semantic_requirements

        ),

    )





def _deduplicate_structured_skill_requirements(

    requirements: list[SearchRequirement],

) -> None:

    """Keep one graph node when the parser repeats the same structured skill."""



    seen: dict[str, SearchRequirement] = {}

    duplicates = []



    for requirement in requirements:

        if not (

            set(requirement.capabilities)

            & {

                "structured_candidate_lookup",

                "structured_experience_lookup",

            }

            and (

                (requirement.field or "").casefold()

                in {"skill", "skills"}

                or (

                    requirement.source_of_truth

                    or ""

                ).casefold()

                == "candidate_skill"

            )

        ):

            continue



        raw_value = (

            requirement.value

            if isinstance(requirement.value, str)

            else (

                requirement.normalized_text

                or requirement.original_text

            )

        )



        skill = re.sub(

            r"^(?:(?:knows?|has|uses?|is\s+familiar\s+with|"

            r"familiar\s+with|has\s+experience\s+with|"

            r"experience\s+with)\s+)+",

            "",

            str(raw_value),

            flags=re.IGNORECASE,

        ).strip()



        key = canonical_term(

            skill,

            "skill",

        )



        if not key:

            continue



        existing = seen.get(key)



        if existing is None:

            seen[key] = requirement

            continue



        if requirement.field and not existing.field:

            requirement.group_id = existing.group_id

            requirement.relationship = existing.relationship

            requirement.negated = existing.negated

            seen[key] = requirement

            duplicates.append(existing)

        else:

            duplicates.append(requirement)



    if duplicates:

        requirements[:] = [

            requirement

            for requirement in requirements

            if requirement not in duplicates

        ]





def _normalize_compound_structured_skills(

    parsed_skills: list[str],

    requirements: list[SearchRequirement],

) -> None:

    """Repair skill nodes that swallowed a neighboring boolean search clause."""



    known_skills = {

        canonical_term(skill, "skill"): skill.strip()

        for skill in parsed_skills

        if skill.strip()

        and not re.search(

            r"\b(?:and|or|not)\b",

            skill,

            re.IGNORECASE,

        )

    }



    for requirement in requirements:

        if (

            (requirement.field or "").casefold()

            not in {"skill", "skills"}

            or not isinstance(

                requirement.value,

                str,

            )

            or not re.search(

                r"\b(?:and|or|not)\b",

                requirement.value,

                re.IGNORECASE,

            )

        ):

            continue



        for other in requirements:

            if (

                other is requirement

                or (

                    (other.field or "").casefold()

                    not in {"skill", "skills"}

                )

                or not isinstance(

                    other.value,

                    str,

                )

                or re.search(

                    r"\b(?:and|or|not)\b",

                    other.value,

                    re.IGNORECASE,

                )

            ):

                continue



            known_skills.setdefault(

                canonical_term(

                    other.value,

                    "skill",

                ),

                other.value.strip(),

            )



        mentioned = [
        skill
        for skill in known_skills.values()
        if re.search(
            rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])",
            requirement.value,
            re.IGNORECASE,
        )
    ]



        unique_mentions = {

            canonical_term(

                skill,

                "skill",

            ): skill

            for skill in mentioned

        }



        if len(unique_mentions) != 1:

            continue



        skill = next(

            iter(unique_mentions.values())

        )



        requirement.value = skill

        requirement.original_text = skill

        requirement.normalized_text = normalize_phrase(

            skill

        )

        requirement.canonical_value = canonical_term(

            skill,

            "skill",

        )

        requirement.equivalent_terms = equivalent_terms(

            skill,

            "skill",

        )





def _normalize_explicit_structured_skill_or(

    query: str,

    requirements: list[SearchRequirement],

) -> None:

    """Mark explicitly written skill alternatives as one structured OR group."""



    skill_requirements = [

        requirement

        for requirement in requirements

        if (

            (requirement.field or "").casefold()

            in {"skill", "skills"}

        )

        and isinstance(

            requirement.value,

            str,

        )

        and requirement.value.strip()

    ]



    mentions = []



    for requirement in skill_requirements:

        aliases = (

            requirement.equivalent_terms

            or equivalent_terms(

                requirement.value,

                "skill",

            )

        )



        probes = set(

            aliases

            + [

                requirement.value,

                requirement.original_text,

            ]

        )



        for probe in probes:

            normalized_probe = " ".join(

                probe.strip().split()

            )



            if not normalized_probe:

                continue



            pattern = re.escape(

                normalized_probe

            ).replace(

                r"**\\&#x20;**",

                r"\s+",

            )



            for match in re.finditer(

                rf"(?<![\w]){pattern}(?![\w])",

                query,

                re.IGNORECASE,

            ):

                mentions.append(

                    (

                        match.start(),

                        match.end(),

                        requirement,

                    )

                )



    unique_mentions = {}



    for start, end, requirement in mentions:

        unique_mentions[

            (

                start,

                end,

                requirement.id,

            )

        ] = (

            start,

            end,

            requirement,

        )



    ordered = sorted(

        unique_mentions.values(),

        key=lambda item: (

            item[0],

            item[1],

        ),

    )



    groups = []



    for left, right in zip(

        ordered,

        ordered[1:],

    ):

        gap = query[

            left[1]:right[0]

        ]



        if not re.fullmatch(

            r"\s\*(?:[,;]\s\*)?or(?:\s\*[,;])?\s\*",

            gap,

            re.IGNORECASE,

        ):

            continue



        if (

            groups

            and groups[-1][-1].id

            == left[2].id

        ):

            groups[-1].append(

                right[2]

            )

        else:

            groups.append(

                [

                    left[2],

                    right[2],

                ]

            )



    for index, group in enumerate(

        groups,

        start=1,

    ):

        group_id = (

            f"explicit_skill_or_{index}"

        )



        for requirement in group:

            requirement.group_id = group_id

            requirement.relationship = "OR"





def _ensure_structured_equivalents(

    requirements: list[SearchRequirement],

) -> None:

    """

    Preserve high-confidence equivalents for structured role/company/skill

    requirements.



    These are retrieval hints only.

    """



    for requirement in requirements:

        field = (

            requirement.field or ""

        ).casefold()



        kind = None



        if field in {"skill", "skills"}:

            kind = "skill"



        elif field in {"role", "roles"}:

            kind = "role"



        elif field in {"company", "companies"}:

            kind = "company"



        if not kind:

            continue



        if not isinstance(

            requirement.value,

            str,

        ):

            continue



        if not requirement.equivalent_terms:

            requirement.equivalent_terms = (

                equivalent_terms(

                    requirement.value,

                    kind,

                )

            )





def _apply_same_experience_relationships(

    query: str,

    requirements: list[SearchRequirement],

) -> None:

    """

    Ensure role + company requirements connected by recruiter wording

    such as 'software developer at TCS' are resolved against the same

    employment record.

    """



    role_requirements = [

        requirement

        for requirement in requirements

        if (

            requirement.field or ""

        ).casefold()

        in {"role", "roles"}

        and isinstance(

            requirement.value,

            str,

        )

    ]



    company_requirements = [

        requirement

        for requirement in requirements

        if (

            requirement.field or ""

        ).casefold()

        in {"company", "companies"}

        and isinstance(

            requirement.value,

            str,

        )

    ]



    if not role_requirements or not company_requirements:

        return



    # Relationship indicators connecting a role to a company.

    role_company_pattern = re.compile(

        r"\b(?:at|with|for|from)\b",

        re.IGNORECASE,

    )



    if not role_company_pattern.search(

        query

    ):

        return



    for role_requirement in role_requirements:

        for company_requirement in company_requirements:

            role_requirement.relationship = (

                "SAME_EXPERIENCE"

            )

            company_requirement.relationship = (

                "SAME_EXPERIENCE"

            )



            role_requirement.related_requirements = list(

                dict.fromkeys(

                    role_requirement.related_requirements

                    + [company_requirement.id]

                )

            )



            company_requirement.related_requirements = list(

                dict.fromkeys(

                    company_requirement.related_requirements

                    + [role_requirement.id]

                )

            )