from time import perf_counter
from sqlalchemy.orm import Session

from app.database.models.experience import Experience
from app.search.normalization import (
    equivalent_terms,
    role_matches as _role_matches,
)

from app.intelligence.validator.rules import (
    _normalize,
    _tokens,
    _format_months,
    _experience_source_label,
    _matched_experience_payload,
    _select_best_matching_experience,
    _company_matches,
    _matching_evidence,
    _experience_requirement_label,
    _supports_negative_technology_evidence,
    _candidate_has_structured_skill,
    _normalize_for_source,
    _resolve_experience_source,
    _experience_duration_months,
    _combined_experience_months,
)

from app.intelligence.validator.heuristics import (
    is_customer_relationship_requirement,
    customer_relationship_partial_evidence,
    customer_relationship_partial_reason,
    _has_ai_concept,
    _is_ai_build_requirement,
    _is_ecommerce_build_requirement,
    _supports_ecommerce_build,
    _is_distributed_system_requirement,
    _supports_distributed_system_design,
    _is_ml_project_requirement,
    _supports_ml_project,
    _supports_ai_build,
    _semantic_support_score,
    _is_specialized_semantic_requirement,
    _heuristic_supports_semantic_requirement,
    _is_microsoft_ecosystem_requirement,
    _is_cloud_technology_requirement,
)

from app.intelligence.validator.structured import validate_structured_requirements
from app.intelligence.validator.semantic import (
    _supports_semantic_requirement,
    validate_semantic_requirements,
    USE_NLI_VALIDATOR,
    verify_evidence_entailment,
)
from app.intelligence.validator.relational import validate_relational_requirements
from app.intelligence.validator.temporal import validate_temporal_requirements

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
    positive_semantic_keys = {
        _normalize(
            str(item.value) if isinstance(item.value, str) else item.normalized_text
        )
        for item in requirements_graph
        if not item.negated
        and "semantic_evidence_retrieval" in item.capabilities
    }
    negated_semantic_keys = {
        _normalize(
            str(item.value) if isinstance(item.value, str) else item.normalized_text
        )
        for item in requirements_graph
        if item.negated
        and "semantic_evidence_retrieval" in item.capabilities
    }
    independent_semantic_requirements = [
        requirement for requirement in semantic_requirements
        if _normalize(requirement) not in grouped_texts
        and (
            _normalize(requirement) not in negated_semantic_keys
            or _normalize(requirement) in positive_semantic_keys
        )
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
                requirement_filter = {
                    "companies": [value],
                    "company_aliases": {
                        value: alternative.equivalent_terms or [value]
                    },
                }
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
        group_matched = any(
            not passed if alternative.negated else passed
            for alternative, passed, _, _ in alternative_results
        )
        if not group_matched:
            structured_valid = False
            structured_failures.append({
                "type": "STRUCTURED_OR",
                "group_id": group_id,
                "required": [item.original_text for item, _ in mapped_alternatives],
                "reason": "No alternative in this requirement group matched the candidate profile",
            })
        for alternative, passed, matches, matched_evidence in alternative_results:
            condition_passed = not passed if alternative.negated else passed
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
                "matched": condition_passed,
                "negated": alternative.negated,
                "evidence": [] if alternative.negated else (
                    matches[0].get("evidence", []) if matches else []
                ),
            })
            if condition_passed and not alternative.negated:
                structured_evidence.extend(matched_evidence)

    for requirement in requirements_graph:
        if (
            not requirement.mandatory
            or not requirement.negated
            or (
                requirement.group_id
                and requirement.relationship.upper() == "OR"
            )
            or not set(requirement.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }
        ):
            continue

        # Negative technology requirements are handled by the evidence-aware
        # block below. A listed skill is not, by itself, a hard exclusion.
        field = (requirement.field or "").casefold()
        if field in {"skill", "skills"}:
            continue
        value = requirement.value
        if field in {"skill", "skills"} and isinstance(value, str):
            requirement_filter = {"skills": [value]}
        elif field in {"role", "roles"} and isinstance(value, str):
            requirement_filter = {"roles": [value]}
        elif field in {"company", "companies"} and isinstance(value, str):
            requirement_filter = {
                "companies": [value],
                "company_aliases": {
                    value: requirement.equivalent_terms or [value]
                },
            }
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
        if not requirement_filter:
            continue
        excluded, _, exclusion_matches, _ = validate_structured_requirements(
            db=db,
            candidate_id=candidate_id,
            requirements=requirement_filter,
            evidence=evidence,
        )
        matched = not excluded
        structured_matches.extend({
            **match,
            "requirement_id": requirement.id,
            "requirement": requirement.original_text,
            "matched": matched,
            "negated": True,
            "mandatory": True,
            "evidence": [],
        } for match in exclusion_matches[:1] or [{
            "type": field.rstrip("s"),
            "candidate_value": None,
        }])
        if excluded:
            structured_valid = False
            structured_failures.append({
                "type": "STRUCTURED_NOT",
                "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": "Candidate matched an explicitly excluded requirement",
            })
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
            if alternative.negated:
                excluded, _, _, _ = validate_semantic_requirements(
                    candidate_id=candidate_id,
                    semantic_requirements=[text],
                    evidence=evidence,
                )
                if not excluded and best is None:
                    best = (0.0, alternative, None)
                continue
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
            if best[2] is not None:
                supporting_evidence.append(best[2])
            for alternative in alternatives:
                matched_requirements.append({
                    "type": "semantic", "requirement_id": alternative.id,
                    "group_id": group_id,
                    "requirement": alternative.original_text,
                    "matched": alternative.id == best[1].id,
                    "relationship": "OR", "mandatory": alternative.mandatory,
                    "negated": alternative.negated,
                    "evidence": (
                        [best[2]]
                        if alternative.id == best[1].id and best[2] is not None
                        else []
                    ),
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
                "mandatory": alternative.mandatory, "negated": alternative.negated,
                "evidence": [],
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
                matched, _, alternative_evidence, matches = validate_semantic_requirements(
                    candidate_id=candidate_id,
                    semantic_requirements=[text],
                    evidence=evidence,
                )
                passed = not matched if alternative.negated else matched
            else:
                field = (alternative.field or "").casefold()
                value = alternative.value
                alternative_type = {"skill": "skill", "skills": "skill", "role": "role", "roles": "role"}.get(field, field)
                if field in {"skill", "skills"} and value:
                    requirement_filter = {"skills": [str(value)]}
                elif field in {"role", "roles"} and value:
                    requirement_filter = {"roles": [str(value)]}
                elif field == "company" and value:
                    requirement_filter = {
                        "companies": [str(value)],
                        "company_aliases": {
                            str(value): alternative.equivalent_terms or [str(value)]
                        },
                    }
                elif field == "location" and value:
                    requirement_filter = {"location": str(value)}
                else:
                    requirement_filter = {}
                if requirement_filter:
                    matched, _, matches, alternative_evidence = validate_structured_requirements(
                        db=db, candidate_id=candidate_id,
                        requirements=requirement_filter, evidence=evidence,
                    )
                    passed = not matched if alternative.negated else matched
            group_passed = group_passed or passed
            if passed and not alternative.negated:
                group_matches.extend(alternative_evidence)
            selected = matches[0] if matches else {}
            if passed and not alternative.negated and selected.get("evidence"):
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
                "negated": alternative.negated,
                "evidence": (
                    []
                    if alternative.negated
                    else selected.get("evidence", alternative_evidence if passed else [])
                ),
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

    grouped_negated_ids = {
        item.id
        for alternatives in all_or_groups.values()
        for item in alternatives
        if item.negated
    }

    # Negative technology requirements are evidence-aware.
    #
    # Examples:
    #   "not Python"
    #       - Python nowhere relevant -> MATCH
    #       - Python only in CandidateSkill -> PARTIAL_MATCH
    #       - Python used in project/experience/meaningful summary -> EXCLUDE
    #
    # This must not be implemented as a simple SQL skill exclusion because a
    # listed skill alone is weaker evidence than actual work performed.
    negative_semantic_partial_ids = set()

    for requirement in requirements_graph:
        field = (requirement.field or "").casefold()
        is_negative_technology = field in {"skill", "skills"}

        if (
            not requirement.mandatory
            or not requirement.negated
            or requirement.id in grouped_negated_ids
            or (
                "semantic_evidence_retrieval" not in requirement.capabilities
                and not is_negative_technology
            )
        ):
            continue

        text = (
            requirement.value
            if isinstance(requirement.value, str)
            else requirement.normalized_text
        )

        negative_work_evidence = None
        negative_work_support_score = 0.0

        for evidence_item in evidence:
            matched_sentence = _supports_negative_technology_evidence(
                requirement=text,
                evidence_text=str(evidence_item.get("text") or ""),
                evidence_type=evidence_item.get("evidence_type"),
            )
            if not matched_sentence:
                continue

            support_score = _semantic_support_score(
                requirement=text,
                sentence=matched_sentence,
                evidence_type=evidence_item.get("evidence_type"),
            )
            if (
                negative_work_evidence is None
                or support_score > negative_work_support_score
            ):
                negative_work_evidence = {
                    **evidence_item,
                    "requirement": text,
                    "text": matched_sentence,
                    "semantic_support_score": support_score,
                }
                negative_work_support_score = support_score

        if negative_work_evidence is not None:
            matched = False
            matched_requirements.append({
                "type": "semantic",
                "requirement_id": requirement.id,
                "requirement": requirement.original_text,
                "matched": matched,
                "negated": True,
                "mandatory": True,
                "evidence": [negative_work_evidence],
            })
            semantic_failures.append({
                "type": "SEMANTIC_NOT",
                "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": (
                    "Excluded technology was found in meaningful project, "
                    "experience, or work-related summary evidence"
                ),
                "evidence": [negative_work_evidence],
            })
            continue

        # If the only evidence is a structured/listed skill, keep the
        # candidate eligible but mark the negative requirement as partial.
        # The final ranking layer can then place these below clean matches.
        skill_only = _candidate_has_structured_skill(
            db=db,
            candidate_id=candidate_id,
            requirement=text,
        )
        if skill_only:
            negative_semantic_partial_ids.add(requirement.id)

        matched_requirements.append({
            "type": "semantic",
            "requirement_id": requirement.id,
            "requirement": requirement.original_text,
            "matched": not skill_only,
            "negated": True,
            "mandatory": True,
            "evidence": [],
            "negative_skill_only": skill_only,
        })

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
        candidate_tenure_value = (
            f"{_format_months(actual_months)} dated role tenure"
            if supporting_sources
            else "No dated supporting experience found"
        )
        supporting_evidence_list = [proof for _, proof in supporting_sources.values()]

        if semantic_match:
            semantic_match["matched"] = duration_matched
            semantic_match["requirement_id"] = requirement.id
            semantic_match["duration_matched"] = duration_matched
            semantic_match["candidate_value"] = candidate_tenure_value
            if supporting_sources:
                semantic_match["evidence"] = supporting_evidence_list
        else:
            matched_requirements.append({
                "type": "relevant_experience",
                "requirement_id": requirement.id,
                "requirement": duration_label,
                "matched": duration_matched,
                "candidate_value": candidate_tenure_value,
                "evidence": supporting_evidence_list,
            })
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
    # Candidate-level CrossEncoder is a ranking signal only.
    # It must not independently approve or reject a candidate.
    candidate_semantic_valid = None

    if candidate_semantic_scores is not None:
        semantic_nodes = [
            item for item in requirements_graph
            if item.mandatory
            and not item.negated
            and "semantic_evidence_retrieval" in item.capabilities
        ]
        nodes_by_id = {item.id: item for item in semantic_nodes}

        def node_score(node):
            value = (
                node.value
                if isinstance(node.value, str)
                else node.normalized_text
            )
            return candidate_semantic_scores.get(
                _normalize(value),
                candidate_semantic_scores.get(_normalize(node.original_text)),
            )

        for match in matched_requirements:
            if match.get("type") != "semantic" or match.get("negated"):
                continue

            requirement_text = str(match.get("requirement") or "")
            node = nodes_by_id.get(match.get("requirement_id"))
            score = node_score(node) if node else None

            if score is None:
                score = candidate_semantic_scores.get(
                    _normalize(requirement_text)
                )

            match["candidate_reranker_score"] = score
            match["candidate_reranker_threshold"] = candidate_semantic_min_score
            match["candidate_score_above_threshold"] = (
                score is not None
                and float(score) >= candidate_semantic_min_score
            )

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
            # Runtime Geoapify location filters are already enforced
            # by the retriever. Do not validate them again using the
            # legacy scalar location matcher.
            is_runtime_location = (
                field == "location"
                and str(requirement.id).startswith("runtime_filter_location_")
                and bool(structured_requirements.get("location_filters"))
            )   
            if is_runtime_location:
                linked = [{
                    "type": "location",
                    "requirement_id": requirement.id,
                    "requirement": requirement.original_text,
                    "matched": True,
                    "evidence": [],
                }]
            else:
                expected_type = {
                    "skill": "skill", 
                    "skills": "skill",
                    "role": "role", 
                    "roles": "role",
                    "company": "company", 
                    "companies": "company",
                    "location": "location",
                    "experience": "experience",
                    "total_experience": "experience",
                    "min_experience_years": "experience",
                    "max_experience_years": "experience",
                    "seniority": "seniority",
                }.get(field)    
                if expected_type:
                    linked = [
                        match for match in matched_requirements
                        if match.get("type") == expected_type
                    ]
        matched = any(bool(match.get("matched")) for match in linked)
        if requirement.group_id and requirement.relationship.upper() == "OR":
            group_nodes = [node for node in requirements_graph
                if node.group_id == requirement.group_id and node.relationship.upper() == "OR"]
            group_matches = [match for node in group_nodes for match in matched_requirements
                if match.get("requirement_id") == node.id]
            matched = any(bool(match.get("matched")) for match in group_matches)
        match_mode = requirement.match_mode or ("HARD" if requirement.mandatory else "SOFT")
        if requirement.id in negative_semantic_partial_ids:
            status = "PARTIAL_MATCH"
        else:
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
        status["status"] == "PARTIAL_MATCH"
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

