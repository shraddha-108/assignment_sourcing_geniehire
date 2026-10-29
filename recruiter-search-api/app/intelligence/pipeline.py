import logging
import uuid
from itertools import product
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models.candidate import Candidate
from app.database.models.candidate_evidence import CandidateEvidence
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.experience import Experience
from app.database.models.project import Project
from app.database.models.project_skill import ProjectSkill
from app.database.models.resume_section import ResumeSection
from app.database.location_utils import format_candidate_location
from app.search.normalization import (
    equivalent_terms,
    industry_evidence_matches,
    industry_evidence_terms,
)

from app.intelligence.consolidator import (
    consolidate_semantic_evidence,
)

from app.intelligence.ranker import (
    rank_candidates,
)
from app.intelligence.planner import build_execution_plan, semantic_candidate_scope
from app.intelligence.observability import rejection_records

from app.intelligence.reranker import (
    CANDIDATE_VALIDATION_MIN_SCORE,
    MAX_CANDIDATE_VALIDATION_PAIRS,
    MAX_CHUNK_RERANK_PAIRS,
    rerank_evidence,
)

from app.intelligence.retriever import (
    retrieve_semantic,
    retrieve_structured_candidates,
)

from app.intelligence.scorer import (
    score_candidates,
)

from app.intelligence.validator import (
    validate_candidate,
)


logger = logging.getLogger(__name__)


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _semantic_debug_chunks(evidence: list[dict], limit: int = 20) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for item in evidence:
        candidate_id = _canonical_candidate_id(item.get("candidate_id"))
        if candidate_id is not None:
            grouped.setdefault(candidate_id, []).append(item)
    ranked = sorted(
        grouped.items(),
        key=lambda pair: max(
            (float(item.get("reranker_score", item.get("retrieval_score", 0.0)) or 0.0)
             for item in pair[1]), default=0.0),
        reverse=True,
    )[:limit]
    result = []
    for candidate_id, items in ranked:
        items.sort(
            key=lambda item: (
                float(item.get("reranker_score", 0.0) or 0.0),
                float(item.get("retrieval_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        result.append({
            "candidate_id": candidate_id,
            "chunks": [{
                "evidence_id": item.get("evidence_id") or item.get("source_id"),
                "requirement": item.get("reranker_query"),
                "evidence_type": item.get("evidence_type"),
                "retrieval_score": item.get("retrieval_score"),
                "chunk_reranker_score": item.get("reranker_score"),
                "text": str(item.get("text") or "")[:480],
            } for item in items[:3]],
        })
    return result


def _build_candidate_validation_inputs(
    requirements: list[str],
    chunk_reranked_evidence: list[dict],
) -> list[dict]:
    candidate_inputs = []
    seen_requirements = set()
    for requirement in requirements:
        requirement_key = _normalize(requirement)
        if not requirement_key or requirement_key in seen_requirements:
            continue
        seen_requirements.add(requirement_key)
        requirement_evidence = [
            item for item in chunk_reranked_evidence
            if requirement_key in {
                _normalize(item.get("reranker_query")),
                *(_normalize(value) for value in item.get("retrieval_requirements", [])),
            }
        ]
        for consolidated in consolidate_semantic_evidence(requirement_evidence):
            chunks = consolidated["evidence"]
            # Keep the candidate-level input focused and below the CrossEncoder
            # token limit while retaining distinct evidence sources.
            evidence_text = "\n".join(
                f"{str(item.get('evidence_type') or 'resume evidence').title()}: "
                f"{str(item.get('text') or '').strip()[:320]}"
                for item in chunks[:3]
                if str(item.get("text") or "").strip()
            )
            if not evidence_text:
                continue
            candidate_inputs.append({
                "candidate_id": consolidated["candidate_id"],
                "requirement": requirement,
                "reranker_query": requirement,
                "text": evidence_text,
                "evidence": chunks,
                "retrieval_score": max(
                    (float(item.get("retrieval_score") or 0.0) for item in chunks),
                    default=0.0,
                ),
                "chunk_reranker_score": consolidated.get("semantic_score"),
            })
    # Keep work bounded across the whole query (not merely per requirement).
    # Round-robin the requirement buckets so one broad requirement cannot
    # consume the candidate-level validation budget.
    by_requirement: dict[str, list[dict]] = {}
    for item in candidate_inputs:
        by_requirement.setdefault(_normalize(item.get("requirement")), []).append(item)
    selected = []
    while len(selected) < MAX_CANDIDATE_VALIDATION_PAIRS and any(by_requirement.values()):
        for bucket in by_requirement.values():
            if bucket and len(selected) < MAX_CANDIDATE_VALIDATION_PAIRS:
                selected.append(bucket.pop(0))
    return selected


def _structured_or_groups(requirements: list) -> list[list]:
    groups: dict[str, list] = {}
    for requirement in requirements:
        if (
            requirement.group_id
            and requirement.relationship.upper() == "OR"
            and requirement.mandatory
            and set(requirement.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }
        ):
            groups.setdefault(requirement.group_id, []).append(requirement)
    return [items for items in groups.values() if len(items) > 1]


def _structured_filter_for_requirement(requirement) -> dict:
    field = (requirement.field or "").casefold()
    value = requirement.value
    if field in {"skill", "skills"} and isinstance(value, str):
        return {"skills": requirement.equivalent_terms or equivalent_terms(value, "skill") or [value]}
    if field in {"role", "roles"} and isinstance(value, str):
        return {"roles": [value]}
    if field in {"company", "companies"} and isinstance(value, str):
        return {"companies": [value]}
    if field == "location" and isinstance(value, str):
        return {"location": value}
    if field in {"experience", "total_experience"} and isinstance(value, dict):
        return {
            "min_experience_years": value.get("min_experience_years"),
            "max_experience_years": value.get("max_experience_years"),
            "min_experience_exclusive": requirement.min_experience_exclusive,
        }
    if field in {"min_experience_years", "max_experience_years"} and value is not None:
        return {field: value}
    return {}


def _mixed_structured_or_branches(requirements: list, base_filter: dict) -> list[dict] | None:
    groups = _structured_or_groups(requirements)
    mixed_groups = []
    for group in groups:
        options = [_structured_filter_for_requirement(item) for item in group]
        options = [option for option in options if option]
        fields = {field for option in options for field, value in option.items() if value is not None}
        needs_branch = len(fields) > 1 or any(
            field not in {"skills", "roles", "companies"}
            for option in options for field, value in option.items() if value is not None
        )
        if len(options) == len(group) and needs_branch:
            mixed_groups.append((group, options))
    if not mixed_groups:
        return None

    branch_count = 1
    for _, options in mixed_groups:
        branch_count *= len(options)
    if branch_count > 32:
        raise ValueError("This search has too many alternative branches. Please split it into simpler searches.")

    base = {
        **base_filter,
        "skills": list(base_filter.get("skills") or []),
        "roles": list(base_filter.get("roles") or []),
        "companies": list(base_filter.get("companies") or []),
    }
    for group, _ in mixed_groups:
        for requirement in group:
            option = _structured_filter_for_requirement(requirement)
            for field, value in option.items():
                if value is None:
                    continue
                if field in {"skills", "roles", "companies"}:
                    removals = {_normalize(str(item)) for item in value}
                    base[field] = [item for item in base[field] if _normalize(str(item)) not in removals]
                elif field in base and _normalize(str(base.get(field))) == _normalize(str(value)):
                    base[field] = None

    branches = []
    for selected_options in product(*(options for _, options in mixed_groups)):
        branch = {
            **base,
            "skills": list(base["skills"]),
            "roles": list(base["roles"]),
            "companies": list(base["companies"]),
        }
        for option in selected_options:
            for field, value in option.items():
                if value is None:
                    continue
                if field in {"skills", "roles", "companies"}:
                    branch[field].extend(value)
                else:
                    branch[field] = value
        branches.append(branch)
    return branches


def _candidate_ids_from_structured(
    structured_results: list[dict],
) -> list[int]:

    return list(
        {
            item["candidate_id"]
            for item in structured_results
            if item.get("candidate_id")
            is not None
        }
    )


def _build_candidate_map(
    db: Session,
    candidate_ids: list[int],
) -> dict[int, Candidate]:

    if not candidate_ids:
        return {}

    candidates = db.scalars(
        select(Candidate)
        .options(
            selectinload(Candidate.experiences).selectinload(Experience.role),
            selectinload(Candidate.experiences).selectinload(Experience.company),
            selectinload(Candidate.education),
            selectinload(Candidate.candidate_skills).selectinload(CandidateSkill.skill),
            selectinload(Candidate.projects).selectinload(Project.skills).selectinload(ProjectSkill.skill),
            selectinload(Candidate.location),
        )
        .where(Candidate.id.in_(candidate_ids))
    ).all()

    return {
        candidate.id: candidate
        for candidate in candidates
    }


def _canonical_candidate_id(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _assemble_candidate_evidence(
    db: Session,
    candidate_ids: list[int],
    qdrant_evidence: list[dict],
) -> dict[int, list[dict]]:
    """Merge actual PostgreSQL resume passages with retrieved Qdrant hits."""
    grouped: dict[int, dict[str, dict]] = {
        candidate_id: {} for candidate_id in candidate_ids
    }

    def key_for(item: dict) -> str:
        source_id = item.get("source_id") or item.get("evidence_id")
        if source_id is not None:
            query_key = _normalize(item.get("reranker_query"))
            if item.get("retrieval_source") == "qdrant" and query_key:
                return f"id:{source_id}:requirement:{query_key}"
            return f"id:{source_id}"
        normalized = " ".join(str(item.get("text") or "").casefold().split())
        return f"text:{normalized}"

    rows = db.scalars(
        select(CandidateEvidence)
        .where(CandidateEvidence.candidate_id.in_(candidate_ids))
        .order_by(CandidateEvidence.id)
    ).all()
    section_ids = {row.resume_section_id for row in rows if row.resume_section_id is not None}
    section_ids.update(
        item.get("resume_section_id")
        for item in qdrant_evidence
        if item.get("resume_section_id") is not None
    )
    section_by_id = {
        section.id: section
        for section in db.scalars(
            select(ResumeSection).where(ResumeSection.id.in_(section_ids))
        ).all()
    } if section_ids else {}
    for row in rows:
        section = section_by_id.get(row.resume_section_id)
        record = {
            "candidate_id": row.candidate_id,
            "evidence_id": row.id,
            "source_id": row.id,
            "resume_id": row.resume_id,
            "resume_section_id": row.resume_section_id,
            "section_type": section.section_type if section else None,
            "section_title": section.title if section else None,
            "evidence_type": row.evidence_type,
            "text": row.text,
            "retrieval_score": 0.0,
            "retrieval_source": "postgresql",
        }
        grouped[row.candidate_id][key_for(record)] = record

    for retrieved in qdrant_evidence:
        candidate_id = _canonical_candidate_id(retrieved.get("candidate_id"))
        if candidate_id not in grouped:
            continue
        record = dict(retrieved)
        record["candidate_id"] = candidate_id
        record["source_id"] = retrieved.get("evidence_id")
        section = section_by_id.get(record.get("resume_section_id"))
        if section:
            record.setdefault("section_type", section.section_type)
            record.setdefault("section_title", section.title)
        key = key_for(record)
        stored = grouped[candidate_id].get(key) or grouped[candidate_id].get(
            f"id:{record.get('source_id')}"
        ) or {}
        grouped[candidate_id][key] = {
            **stored,
            **record,
            "text": stored.get("text") or record.get("text") or "",
            "retrieval_source": "qdrant",
        }

    return {
        candidate_id: sorted(
            records.values(),
            key=lambda item: float(item.get("retrieval_score") or 0.0),
            reverse=True,
        )
        for candidate_id, records in grouped.items()
    }


def _select_evidence_for_reranking(
    evidence_by_candidate: dict[int, list[dict]],
    include_postgres_evidence: bool,
) -> list[dict]:
    primary = []
    secondary = []
    for candidate_id, evidence in evidence_by_candidate.items():
        qdrant_hits = [
            item for item in evidence
            if item.get("retrieval_source") == "qdrant"
        ][:3]
        stored_evidence = []
        if include_postgres_evidence:
            stored_evidence = [
                item for item in evidence
                if item.get("retrieval_source") == "postgresql"
                and str(item.get("evidence_type") or "").casefold()
                not in {"skill", "skills", "education"}
            ][:2]
        industry_records = [
            item for item in stored_evidence
            if item.get("source_kind") == "experience_record"
            and item.get("retrieval_requirements")
        ][:1]
        candidate_primary = qdrant_hits[:1] + industry_records
        if not candidate_primary:
            candidate_primary = stored_evidence[:1]
        primary.extend(candidate_primary)
        secondary.extend(qdrant_hits[1:] + [
            item for item in stored_evidence[1:]
            if item not in industry_records
        ])

    # Keep one representative passage per candidate before spending the
    # remaining reranker budget on extra passages. This bounds latency while
    # preserving broad candidate coverage for searches requesting 10 results.
    max_pairs = MAX_CHUNK_RERANK_PAIRS
    primary.sort(key=lambda item: float(item.get("retrieval_score") or 0.0), reverse=True)
    secondary.sort(key=lambda item: float(item.get("retrieval_score") or 0.0), reverse=True)
    selected = primary[:max_pairs]
    remaining = max_pairs - len(selected)
    if remaining > 0:
        selected.extend(secondary[:remaining])
    return selected


def _add_dated_industry_evidence(
    evidence_by_candidate: dict[int, list[dict]],
    candidates_by_id: dict[int, Candidate],
    semantic_requirements: list[str],
) -> None:
    """Make dated employer records available for industry evidence checks and reranking."""
    industry_requirements = list(dict.fromkeys(
        requirement for requirement in semantic_requirements
        if industry_evidence_terms(requirement)
    ))
    if not industry_requirements:
        return

    for candidate_id, candidate in candidates_by_id.items():
        records = evidence_by_candidate.setdefault(candidate_id, [])
        existing_ids = {item.get("experience_id") for item in records}
        for experience in candidate.experiences or []:
            if experience.id in existing_ids:
                continue
            company = experience.company.name if experience.company else ""
            role = experience.role.title if experience.role else "Experience"
            description = (experience.description or "").strip()
            for requirement in industry_requirements:
                if not (
                    industry_evidence_matches(company, requirement)
                    or industry_evidence_matches(description, requirement)
                ):
                    continue
                dates = " - ".join(filter(None, [
                    experience.start_date.strftime("%b %Y") if experience.start_date else None,
                    "Present" if experience.is_current else (
                        experience.end_date.strftime("%b %Y") if experience.end_date else None
                    ),
                ]))
                header = f"{role} at {company}" if company else role
                text = f"{header} ({dates}). {description}".strip()
                records.append({
                    "candidate_id": candidate_id,
                    "evidence_id": f"experience:{experience.id}",
                    "experience_id": experience.id,
                    "source_kind": "experience_record",
                    "evidence_type": "experience",
                    "text": text,
                    "retrieval_score": 0.1,
                    "retrieval_source": "postgresql",
                    "reranker_query": requirement,
                    "retrieval_requirements": [requirement],
                })
                break
        records.sort(
            key=lambda item: float(item.get("retrieval_score") or 0.0),
            reverse=True,
        )


def _build_explanation(matched_requirements: list[dict]) -> list[str]:
    labels = {
        "skill": "Skill matched",
        "role": "Role matched",
        "company": "Company matched",
        "location": "Location matched",
    }
    explanations = []
    for item in matched_requirements:
        kind = item.get("type")
        value = item.get("candidate_value")
        requirement = item.get("requirement")
        if kind == "experience":
            explanations.append(f"Experience: {value} (required: {requirement}).")
        elif kind == "semantic":
            explanations.append(f"Resume evidence supports: {requirement}.")
        elif kind in labels and value:
            explanations.append(f"{labels[kind]}: {value}.")
    return explanations


def _build_experience_timeline(candidate: Candidate) -> list[dict]:
    entries = []
    for experience in candidate.experiences or []:
        role = experience.role.title if experience.role else None
        company = experience.company.name if experience.company else None
        if not role and not company:
            continue
        entries.append({
            "role": role,
            "company": company,
            "start_date": experience.start_date.isoformat() if experience.start_date else None,
            "end_date": experience.end_date.isoformat() if experience.end_date else None,
            "is_current": bool(experience.is_current),
            "duration_months": experience.duration_months,
            "description": experience.description[:4000] if experience.description else None,
        })
    entries.sort(
        key=lambda entry: entry["start_date"] or "",
        reverse=True,
    )
    return entries[:5]


def execute_search(
    db: Session,
    query: str,
    routing_packet,
    trace: dict | None = None,
) -> list[dict]:
    """
    Main Intelligence Layer pipeline.

    Search Layer:
        query → RoutingPacket

    Intelligence Layer:
        RoutingPacket
            ↓
        PostgreSQL / Qdrant retrieval
            ↓
        evidence consolidation
            ↓
        CrossEncoder reranking
            ↓
        requirement validation
            ↓
        scoring
            ↓
        ranking
    """

    started_at = perf_counter()
    search_id = (trace or {}).get("search_id") or str(uuid.uuid4())
    if trace is not None:
        trace.update({"search_id": search_id, "stages": [], "rejections": []})
    debug_enabled = bool(trace and trace.get("debug"))
    structured_started = started_at
    specification = (
        routing_packet.specification
    )

    requested_count = (
        specification.requested_count
    )

    route = routing_packet.route

    requirements = list(getattr(routing_packet, "requirements", []) or [])
    execution_plan = build_execution_plan(requirements)
    if trace is not None:
        trace["execution_plan"] = execution_plan
        trace["routing_packet"] = routing_packet.model_dump(exclude_none=True)

    structured_requirements = dict(routing_packet.structured_requirements)
    semantic_requirements = list(routing_packet.semantic_requirements)
    hard_semantic_requirements = semantic_requirements
    if requirements:
        structured_requirements = {
            "skills": [], "roles": [], "companies": [], "location": None,
            "min_experience_years": None, "max_experience_years": None,
            "min_experience_exclusive": False, "skill_aliases": {},
        }
        graph_semantic = []
        hard_semantic_requirements = []
        for requirement in requirements:
            value = requirement.value
            if requirement.mandatory and set(requirement.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }:
                field = requirement.field
                if field in {"skill", "skills", "role", "roles", "company", "companies"} and value:
                    target_field = {"skill": "skills", "role": "roles", "company": "companies"}.get(field, field)
                    values = value if isinstance(value, list) else [value]
                    for raw_value in values:
                        canonical = (
                            requirement.canonical_value
                            if isinstance(value, str) and requirement.canonical_value
                            else str(raw_value)
                        )
                        if canonical not in structured_requirements[target_field]:
                            structured_requirements[target_field].append(canonical)
                        if target_field == "skills":
                            aliases = requirement.equivalent_terms if isinstance(value, str) else equivalent_terms(canonical, "skill")
                            if aliases:
                                structured_requirements["skill_aliases"][canonical] = aliases
                elif field == "location" and value:
                    structured_requirements["location"] = str(value)
                elif field == "experience" and isinstance(value, dict):
                    structured_requirements["min_experience_years"] = value.get("min_experience_years")
                    structured_requirements["max_experience_years"] = value.get("max_experience_years")
                    structured_requirements["min_experience_exclusive"] = requirement.min_experience_exclusive
                elif field == "min_experience_years" and value is not None:
                    structured_requirements["min_experience_years"] = value
                    structured_requirements["min_experience_exclusive"] = requirement.min_experience_exclusive
                elif field == "max_experience_years" and value is not None:
                    structured_requirements["max_experience_years"] = value
            if "semantic_evidence_retrieval" in requirement.capabilities:
                semantic_text = (
                    value.strip()
                    if isinstance(value, str) and value.strip()
                    else requirement.normalized_text.strip()
                )
                if semantic_text:
                    graph_semantic.append(semantic_text)
                    if requirement.mandatory:
                        hard_semantic_requirements.append(semantic_text)
        semantic_requirements = graph_semantic

    or_groups: dict[str, list] = {}
    for requirement in requirements:
        if requirement.group_id and requirement.relationship.upper() == "OR" and requirement.mandatory:
            or_groups.setdefault(requirement.group_id, []).append(requirement)
    has_mixed_structured_semantic_or = any(
        any("semantic_evidence_retrieval" in item.capabilities for item in group)
        and any(set(item.capabilities) & {
            "structured_candidate_lookup", "structured_experience_lookup"
        } for item in group)
        for group in or_groups.values()
    )
    graph_has_structured_hard = not has_mixed_structured_semantic_or and any(
        requirement.type == "STRUCTURED" and requirement.mandatory
        and not (requirement.group_id and requirement.relationship.upper() == "OR")
        and bool(set(requirement.capabilities) & {
            "structured_candidate_lookup", "structured_experience_lookup"
        })
        for requirement in requirements
    )
    if requirements and graph_has_structured_hard and not any(structured_requirements.values()):
        # Backwards-compatible fallback for parser graph nodes that carry
        # source/capability metadata but omitted legacy field/value details.
        structured_requirements = dict(routing_packet.structured_requirements)

    stages = {item["stage"] for item in execution_plan["stages"]}
    requires_structured = "structured_filter" in stages
    requires_semantic = "semantic_retrieval" in stages

    logger.info(
        "SEARCH START search_id=%s query=%r route=%s requirements=%s dependencies=%s execution_plan=%s",
        search_id,
        query,
        route,
        [item.model_dump(exclude_none=True) for item in requirements],
        {item.id: item.dependencies for item in requirements},
        execution_plan,
    )

    # ==================================================
    # 1. STRUCTURED DISCOVERY
    # ==================================================

    structured_results = []
    structured_branches = _mixed_structured_or_branches(
        requirements,
        structured_requirements,
    )

    if requires_structured and (
        any(structured_requirements.values())
        or not requires_semantic
    ):
        if structured_branches:
            structured_by_candidate = {}
            for branch in structured_branches:
                for item in retrieve_structured_candidates(
                    db=db,
                    requirements=branch,
                ):
                    structured_by_candidate[item["candidate_id"]] = item
            structured_results = list(structured_by_candidate.values())
        else:
            structured_results = retrieve_structured_candidates(
                db=db,
                requirements=structured_requirements,
            )

    structured_candidate_ids = (
        _candidate_ids_from_structured(
            structured_results
        )
    )
    structured_retrieval_seconds = perf_counter() - structured_started
    logger.info(
        "SEARCH STAGE search_id=%s stage=structured_retrieval status=%s candidates=%d duration_s=%.3f",
        search_id,
        "complete" if requires_structured else "skipped",
        len(structured_results),
        structured_retrieval_seconds,
    )
    if trace is not None and "structured_filter" in stages:
        trace["stages"].append({"stage": "structured_filter", "input_count": None,
            "output_count": len(structured_results), "duration_seconds": structured_retrieval_seconds})

    # ==================================================
    # 2. SEMANTIC DISCOVERY
    #
    # Semantic retrieval uses the union of structured matches when mandatory
    # structured criteria are present, so those criteria remain hard constraints.
    # ==================================================

    semantic_evidence = []
    semantic_retrieval_seconds = 0.0

    semantic_scope = semantic_candidate_scope(
        graph_has_structured_hard, structured_candidate_ids
    )
    if requires_semantic and semantic_requirements and semantic_scope != []:

        semantic_started = perf_counter()
        semantic_evidence = retrieve_semantic(
            query=query,
            semantic_requirements=semantic_requirements,
            candidate_ids=semantic_scope,
        )
        semantic_retrieval_seconds = perf_counter() - semantic_started
    if trace is not None and "semantic_retrieval" in stages:
        trace["stages"].append({"stage": "semantic_retrieval",
            "input_count": len(structured_candidate_ids) if structured_candidate_ids else None,
            "output_count": len(semantic_evidence), "duration_seconds": semantic_retrieval_seconds})
    logger.info(
        "SEARCH STAGE search_id=%s stage=semantic_retrieval status=%s evidence=%d candidates=%d duration_s=%.3f",
        search_id,
        "complete" if requires_semantic and semantic_scope != [] else "skipped",
        len(semantic_evidence),
        len({item.get("candidate_id") for item in semantic_evidence}),
        semantic_retrieval_seconds,
    )

    semantic_candidate_ids = {
        candidate_id
        for evidence_item in semantic_evidence
        if (candidate_id := _canonical_candidate_id(
            evidence_item.get("candidate_id")
        )) is not None
    }
    if debug_enabled:
        trace["semantic_debug"] = {
            "requirements": list(hard_semantic_requirements),
            "retrieval": {
                "evidence_count": len(semantic_evidence),
                "candidate_ids": sorted(semantic_candidate_ids),
                "top_chunks": _semantic_debug_chunks(semantic_evidence),
            },
        }

    # ==================================================
    # 5. UNION CANDIDATE DISCOVERY
    #
    # Structured candidates + semantic candidates.
    # ==================================================

    candidate_ids = set(
        structured_candidate_ids
    )

    candidate_ids.update(semantic_candidate_ids)

    reranked_evidence = []
    rerank_seconds = 0.0

    if not candidate_ids:
        logger.info(
            "SEARCH DEBUG route=%s postgres=%d qdrant_candidates=0 union=0 validated=0 final=0 postgres_s=%.3f qdrant_s=%.3f rerank_s=%.3f total_s=%.3f",
            route,
            len(structured_candidate_ids),
            structured_retrieval_seconds,
            semantic_retrieval_seconds,
            rerank_seconds,
            perf_counter() - started_at,
        )
        if trace is not None:
            trace["counts"] = {"structured_candidates": len(structured_candidate_ids),
                "semantic_candidates": 0, "union": 0, "validated": 0, "final": 0}
            trace["duration_seconds"] = perf_counter() - started_at
        return []

    candidate_map = (
        _build_candidate_map(
            db=db,
            candidate_ids=list(
                candidate_ids
            ),
        )
    )

    assembled_evidence = _assemble_candidate_evidence(
        db=db,
        candidate_ids=list(candidate_ids),
        qdrant_evidence=semantic_evidence,
    )
    _add_dated_industry_evidence(
        evidence_by_candidate=assembled_evidence,
        candidates_by_id=candidate_map,
        semantic_requirements=semantic_requirements,
    )

    # Evidence is assembled across the fused candidate pool before reranking.
    # Limit per-candidate passages to control latency while retaining stored
    # resume evidence for PostgreSQL-discovered candidates in hybrid searches.
    evidence_to_rerank = _select_evidence_for_reranking(
        assembled_evidence,
        include_postgres_evidence=bool(semantic_requirements),
    )
    if evidence_to_rerank:
        rerank_started = perf_counter()
        reranked_evidence = rerank_evidence(
            query=query,
            evidence=evidence_to_rerank,
        )
        rerank_seconds = perf_counter() - rerank_started
    if trace is not None:
        trace["stages"].append({"stage": "chunk_reranking",
            "input_count": len(evidence_to_rerank), "output_count": len(reranked_evidence),
            "duration_seconds": rerank_seconds})
    logger.info(
        "SEARCH STAGE search_id=%s stage=chunk_reranking status=%s evidence_in=%d evidence_out=%d duration_s=%.3f",
        search_id,
        "complete" if evidence_to_rerank else "skipped",
        len(evidence_to_rerank),
        len(reranked_evidence),
        rerank_seconds,
    )

    reranked_by_key = {}
    for item in reranked_evidence:
        evidence_id = item.get("source_id") or item.get("evidence_id")
        key = (item.get("candidate_id"), str(evidence_id), _normalize(item.get("reranker_query")))
        reranked_by_key[key] = item

    for candidate_id, records in assembled_evidence.items():
        for index, record in enumerate(records):
            evidence_id = record.get("source_id") or record.get("evidence_id")
            reranked = reranked_by_key.get((candidate_id, str(evidence_id), _normalize(record.get("reranker_query"))))
            if reranked:
                records[index] = {**record, **reranked}

    consolidation_started = perf_counter()
    chunk_candidate_order = [
        item["candidate_id"]
        for item in consolidate_semantic_evidence(reranked_evidence)
    ]
    candidate_validation_inputs = _build_candidate_validation_inputs(
        semantic_requirements,
        reranked_evidence,
    )
    candidate_consolidation_seconds = perf_counter() - consolidation_started
    if trace is not None and candidate_validation_inputs:
        trace["stages"].append({
            "stage": "candidate_consolidation",
            "input_count": len(reranked_evidence),
            "output_count": len(candidate_validation_inputs),
            "duration_seconds": candidate_consolidation_seconds,
        })
    candidate_reranked_evidence = []
    candidate_validation_seconds = 0.0
    if candidate_validation_inputs:
        candidate_validation_started = perf_counter()
        candidate_reranked_evidence = rerank_evidence(
            query=query,
            evidence=candidate_validation_inputs,
        )
        candidate_validation_seconds = perf_counter() - candidate_validation_started
    candidate_semantic_scores_by_id: dict[int, dict[str, float]] = {}
    candidate_semantic_evidence_by_id: dict[int, dict[str, list[dict]]] = {}
    for item in candidate_reranked_evidence:
        candidate_id = _canonical_candidate_id(item.get("candidate_id"))
        if candidate_id is None:
            continue
        requirement_key = _normalize(item.get("requirement"))
        candidate_semantic_scores_by_id.setdefault(candidate_id, {})[
            requirement_key
        ] = float(item.get("reranker_score") or 0.0)
        candidate_semantic_evidence_by_id.setdefault(candidate_id, {})[
            requirement_key
        ] = [{
            **chunk,
            "requirement": item.get("requirement"),
            "candidate_reranker_score": item.get("reranker_score"),
        } for chunk in item.get("evidence", [])[:3]]
    for requirement in requirements:
        if "semantic_evidence_retrieval" not in requirement.capabilities:
            continue
        value_text = (
            requirement.value if isinstance(requirement.value, str)
            else requirement.normalized_text
        )
        score_key = _normalize(value_text)
        original_key = _normalize(requirement.original_text)
        if not score_key or not original_key or score_key == original_key:
            continue
        for scores in candidate_semantic_scores_by_id.values():
            if score_key in scores:
                scores[original_key] = scores[score_key]

    logger.info(
        "SEARCH STAGE search_id=%s stage=candidate_semantic_validation status=%s candidates=%d evidence_pairs=%d duration_s=%.3f raw_score_threshold=%.4f",
        search_id,
        "complete" if candidate_validation_inputs else "skipped",
        len(candidate_semantic_scores_by_id),
        len(candidate_validation_inputs),
        candidate_validation_seconds,
        CANDIDATE_VALIDATION_MIN_SCORE,
    )
    if trace is not None and candidate_validation_inputs:
        trace["stages"].append({
            "stage": "candidate_semantic_validation",
            "input_count": len(candidate_validation_inputs),
            "output_count": sum(
                float(item.get("reranker_score") or 0.0) >= CANDIDATE_VALIDATION_MIN_SCORE
                for item in candidate_reranked_evidence
            ),
            "duration_seconds": candidate_validation_seconds,
        })
    if debug_enabled:
        trace["semantic_debug"].update({
            "chunk_reranking": {
                "evidence_count": len(reranked_evidence),
                "candidate_order": chunk_candidate_order,
                "top_chunks": _semantic_debug_chunks(reranked_evidence),
            },
            "candidate_consolidation": {
                "candidate_count": len(candidate_validation_inputs),
                "top_evidence": [{
                    "candidate_id": item.get("candidate_id"),
                    "requirement": item.get("requirement"),
                    "chunks": [{
                        "evidence_type": chunk.get("evidence_type"),
                        "chunk_reranker_score": chunk.get("reranker_score"),
                        "text": str(chunk.get("text") or "")[:480],
                    } for chunk in item.get("evidence", [])[:3]],
                } for item in candidate_validation_inputs[:60]],
            },
            "candidate_validation": {
                "score_type": "raw CrossEncoder relevance score; not a probability",
                "minimum_score": CANDIDATE_VALIDATION_MIN_SCORE,
                "scores": [{
                    "candidate_id": item.get("candidate_id"),
                    "requirement": item.get("requirement"),
                    "raw_score": item.get("reranker_score"),
                    "passed_score_threshold": float(item.get("reranker_score") or 0.0)
                        >= CANDIDATE_VALIDATION_MIN_SCORE,
                    "consolidated_evidence": str(item.get("text") or "")[:1000],
                } for item in candidate_reranked_evidence[:100]],
            },
        })

    consolidated_semantic = consolidate_semantic_evidence(
        reranked_evidence
    )
    semantic_map = {
        candidate_id: item
        for item in consolidated_semantic
        if (candidate_id := _canonical_candidate_id(
            item.get("candidate_id")
        )) in semantic_candidate_ids
    }

    # ==================================================
    # 6. BUILD CANDIDATE OBJECTS
    # ==================================================

    candidates = []

    for candidate_id in candidate_ids:

        candidate = candidate_map.get(
            candidate_id
        )

        if candidate is None:
            continue

        semantic_item = semantic_map.get(
            candidate_id
        )

        evidence = assembled_evidence.get(candidate_id, [])

        candidates.append(
            {
                "candidate": candidate,
                "candidate_id": candidate_id,
                "evidence": evidence,
                "structured_match": (
                    graph_has_structured_hard
                    and candidate_id in structured_candidate_ids
                ),
                "semantic_match": semantic_item is not None,
                "semantic_score": (
                    semantic_item.get("semantic_score", 0.0)
                    if semantic_item else 0.0
                ),
                "source": (
                    "hybrid"
                    if (
                    graph_has_structured_hard
                    and candidate_id in structured_candidate_ids
                        and semantic_item
                    )
                    else (
                        "structured"
                        if graph_has_structured_hard
                        and candidate_id in structured_candidate_ids
                        else "semantic"
                        if semantic_item
                        else "candidate_pool"
                    )
                ),
            }
        )

    # ==================================================
    # 7. REQUIREMENT VALIDATION
    # ==================================================

    validated_candidates = []
    validation_started = perf_counter()
    temporal_seconds = 0.0
    temporal_checks = 0
    temporal_passes = 0
    relational_seconds = 0.0
    relational_checks = 0
    relational_passes = 0
    evidence_validation_seconds = 0.0
    evidence_validation_passes = 0
    qualification_seconds = 0.0

    for item in candidates:

        validation = validate_candidate(
            db=db,
            candidate_id=item[
                "candidate_id"
            ],
            structured_requirements=(
                structured_requirements
            ),
            semantic_requirements=hard_semantic_requirements,
            evidence=item[
                "evidence"
            ],
            requirements_graph=requirements,
            candidate_semantic_scores=(
                candidate_semantic_scores_by_id.get(item["candidate_id"], {})
                if hard_semantic_requirements else None
            ),
            candidate_semantic_min_score=CANDIDATE_VALIDATION_MIN_SCORE,
            soft_semantic_scores=candidate_semantic_scores_by_id.get(item["candidate_id"], {}),
            soft_semantic_evidence=candidate_semantic_evidence_by_id.get(item["candidate_id"], {}),
        )

        item["validation"] = validation
        item["baseline_validation"] = {
            **validation,
            "matched_requirements": validation.get("baseline_matched_requirements", []),
        }
        evidence_validation_seconds += float(
            validation.get("evidence_validation_duration_seconds") or 0.0
        )
        qualification_seconds += float(
            validation.get("qualification_duration_seconds") or 0.0
        )
        if not any(failure.get("type") in {"SEMANTIC", "CANDIDATE_SEMANTIC"}
            for failure in validation.get("failures", [])):
            evidence_validation_passes += 1
        relational_seconds += float(validation.get("relational_duration_seconds") or 0.0)
        relational_matches = [match for match in validation.get("matched_requirements", [])
            if match.get("type") == "relational"]
        relational_checks += len(relational_matches)
        relational_passes += sum(bool(match.get("matched")) for match in relational_matches)
        temporal_seconds += float(validation.get("temporal_duration_seconds") or 0.0)
        temporal_matches = [match for match in validation.get("matched_requirements", [])
            if match.get("type") == "temporal"]
        temporal_checks += len(temporal_matches)
        temporal_passes += sum(bool(match.get("matched")) for match in temporal_matches)

        for failure in validation.get("failures", []):
            if failure.get("requirement_id"):
                continue
            required = str(failure.get("required") or "").casefold().strip()
            matched_requirement = next((requirement for requirement in requirements
                if required and required in {
                    str(requirement.value or "").casefold().strip(),
                    requirement.original_text.casefold().strip(),
                    requirement.normalized_text.casefold().strip(),
                }), None)
            if matched_requirement:
                failure["requirement_id"] = matched_requirement.id

        if validation["valid"]:
            item["evidence"] = validation["supporting_evidence"]
            item["ranking_evidence"] = assembled_evidence.get(item["candidate_id"], [])

            validated_candidates.append(
                item
            )
        else:
            rejections = []
            for failure in validation.get("failures", []):
                failure_type = failure.get("type")
                failure_stage = (
                    "temporal_validation" if failure_type == "TEMPORAL"
                    else "relationship_resolution" if failure_type == "RELATIONAL"
                    else "evidence_validation" if failure_type in {"SEMANTIC", "CANDIDATE_SEMANTIC"}
                    else "qualification"
                )
                rejections.extend(rejection_records(
                    item["candidate_id"], failure_stage, [failure]
                ))
            logger.info("SEARCH REJECT search_id=%s candidate_id=%s failures=%s",
                search_id, item["candidate_id"], validation.get("failures", []))
            if trace is not None:
                trace["rejections"].extend(rejections)

        if debug_enabled:
            trace["semantic_debug"].setdefault("qualification", []).append({
                "candidate_id": item["candidate_id"],
                "legacy_validation_passed": validation.get("baseline_valid"),
                "legacy_requirement_decisions": validation.get("baseline_requirement_decisions", []),
                "candidate_semantic_passed": validation.get("candidate_semantic_valid"),
                "qualified": validation.get("valid"),
                "requirement_decisions": [{
                    "requirement": match.get("requirement"),
                    "matched": match.get("matched"),
                    "candidate_reranker_score": match.get("candidate_reranker_score"),
                    "candidate_reranker_threshold": match.get("candidate_reranker_threshold"),
                } for match in validation.get("matched_requirements", [])
                    if match.get("type") == "semantic"],
                "failures": validation.get("failures", [])[:8],
            })

    validation_seconds = perf_counter() - validation_started
    logger.info(
        "SEARCH STAGE search_id=%s stage=requirement_validation status=complete candidates_in=%d candidates_out=%d duration_s=%.3f",
        search_id,
        len(candidates),
        len(validated_candidates),
        validation_seconds,
    )
    if trace is not None:
        validation_stage_metrics = {}
        if "evidence_validation" in stages:
            validation_stage_metrics["evidence_validation"] = {
                "stage": "evidence_validation", "input_count": len(candidates),
                "output_count": evidence_validation_passes,
                "duration_seconds": evidence_validation_seconds,
            }
        if temporal_checks:
            validation_stage_metrics["temporal_validation"] = {
                "stage": "temporal_validation", "input_count": temporal_checks,
                "output_count": temporal_passes, "duration_seconds": temporal_seconds,
            }
        if relational_checks:
            validation_stage_metrics["relationship_resolution"] = {
                "stage": "relationship_resolution", "input_count": relational_checks,
                "output_count": relational_passes, "duration_seconds": relational_seconds,
            }
        validation_stage_metrics["qualification"] = {
            "stage": "qualification", "input_count": len(candidates),
            "output_count": len(validated_candidates), "duration_seconds": qualification_seconds,
        }
        for planned_stage in execution_plan["stages"]:
            record = validation_stage_metrics.get(planned_stage["stage"])
            if record:
                trace["stages"].append(record)

    if not validated_candidates:
        logger.info(
            "SEARCH DEBUG route=%s postgres=%d qdrant_candidates=%d union=%d validated=0 final=0 postgres_s=%.3f qdrant_s=%.3f rerank_s=%.3f validation_s=%.3f total_s=%.3f",
            route,
            len(structured_candidate_ids),
            len(semantic_map),
            len(candidate_ids),
            structured_retrieval_seconds,
            semantic_retrieval_seconds,
            rerank_seconds,
            validation_seconds,
            perf_counter() - started_at,
        )
        if trace is not None:
            if debug_enabled:
                legacy_candidates = [item for item in candidates
                                     if item.get("validation", {}).get("baseline_valid")]
                legacy_candidates = [{**item, "validation": item["baseline_validation"]}
                                     for item in legacy_candidates]
                legacy_scored = score_candidates(legacy_candidates, structured_requirements)
                legacy_ranked = rank_candidates(legacy_scored, requested_count)
                trace["semantic_debug"]["legacy_result_ids"] = [
                    item.get("candidate_id") for item in legacy_ranked
                ]
                trace["semantic_debug"]["candidate_validation_passed_ids"] = sorted({
                    row["candidate_id"]
                    for row in trace["semantic_debug"].get("qualification", [])
                    if row.get("candidate_semantic_passed")
                })
                trace["semantic_debug"]["qualified_result_ids"] = []
            if "ranking" in stages:
                trace["stages"].append({"stage": "ranking", "input_count": 0,
                    "output_count": 0, "duration_seconds": 0.0})
            trace["counts"] = {"structured_candidates": len(structured_candidate_ids),
                "semantic_candidates": len(semantic_candidate_ids), "union": len(candidate_ids),
                "validated": 0, "final": 0}
            trace["duration_seconds"] = perf_counter() - started_at
        return []

    # ==================================================
    # 8. SCORE
    # ==================================================

    scored_candidates = score_candidates(
        candidates=validated_candidates,
        structured_requirements=(
            structured_requirements
        ),
    )

    # ==================================================
    # 9. RANK
    # ==================================================

    ranked_candidates = rank_candidates(
        candidates=scored_candidates,
        requested_count=requested_count,
    )
    if trace is not None:
        trace["stages"].append({"stage": "ranking", "input_count": len(scored_candidates),
            "output_count": len(ranked_candidates), "duration_seconds": 0.0})
        if debug_enabled:
            legacy_candidates = [item for item in candidates
                                 if item.get("validation", {}).get("baseline_valid")]
            legacy_candidates = [{**item, "validation": item["baseline_validation"]}
                                 for item in legacy_candidates]
            legacy_scored = score_candidates(legacy_candidates, structured_requirements)
            legacy_ranked = rank_candidates(legacy_scored, requested_count)
            trace["semantic_debug"]["legacy_result_ids"] = [
                item.get("candidate_id") for item in legacy_ranked
            ]
            trace["semantic_debug"]["qualified_result_ids"] = [
                item.get("candidate_id") for item in ranked_candidates
            ]
            trace["semantic_debug"]["candidate_validation_passed_ids"] = sorted({
                row["candidate_id"]
                for row in trace["semantic_debug"].get("qualification", [])
                if row.get("candidate_semantic_passed")
            })

    # ==================================================
    # 10. Final recruiter-facing shape
    # ==================================================

    results = []

    requested_skills = {
        " ".join(str(skill).lower().split())
        for skill in structured_requirements.get("skills", [])
        if skill
    }
    requested_skill_aliases = structured_requirements.get("skill_aliases", {})

    for item in ranked_candidates:

        candidate = item[
            "candidate"
        ]

        validation = item.get("validation", {})
        matched_requirements = validation.get("matched_requirements", [])
        explanation = _build_explanation(matched_requirements)

        matched_skills = []

        if requested_skills:
            for candidate_skill in candidate.candidate_skills:
                skill = candidate_skill.skill

                if skill is None:
                    continue

                normalized_name = " ".join(
                    skill.normalized_name.lower().split()
                )

                if not any(
                    normalized_name in {
                        " ".join(str(alias).casefold().split())
                        for alias in requested_skill_aliases.get(requested, [requested])
                    }
                    for requested in requested_skills
                ):
                    continue

                matched_skills.append(
                    {
                        "skill": skill.name,
                        "last_used_date": (
                            candidate_skill.last_used_date.isoformat()
                            if candidate_skill.last_used_date
                            else None
                        ),
                        "total_months": candidate_skill.months_of_experience,
                    }
                )

        results.append(
            {
                "candidate_id": candidate.id,
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "headline": candidate.headline,
                "location": format_candidate_location(candidate.location),
                "summary": candidate.summary,
                "linkedin_url": candidate.linkedin_url,
                "github_url": candidate.github_url,
                "portfolio_url": candidate.portfolio_url,
                "total_experience_months": (
                    candidate.total_experience_months
                ),
                "experience_timeline": _build_experience_timeline(candidate),
                "education": [
                    {
                        "institution": education.institution,
                        "degree": education.degree,
                        "field_of_study": education.field_of_study,
                        "start_date": education.start_date.isoformat() if education.start_date else None,
                        "end_date": education.end_date.isoformat() if education.end_date else None,
                    }
                    for education in (candidate.education or [])
                ],
                "profile_skills": sorted({
                    row.skill.name
                    for row in (candidate.candidate_skills or [])
                    if row.skill and row.skill.name
                }, key=str.casefold),
                "projects": [
                    {
                        "title": project.title,
                        "description": project.description[:4000] if project.description else None,
                        "url": project.url,
                        "skills": sorted({
                            item.skill.name
                            for item in (project.skills or [])
                            if item.skill and item.skill.name
                        }, key=str.casefold),
                    }
                    for project in (candidate.projects or [])
                ],
                "matched_skills": matched_skills,
                "matched_requirements": matched_requirements,
                "explanation": explanation,
                "retrieval": {
                    "structured_match": item.get("structured_match", False),
                    "semantic_match": item.get("semantic_match", False),
                    "semantic_score": item.get("semantic_score", 0.0),
                },
                "match_status": validation.get("match_status", "MATCH"),
                "score": round(
                    float(
                        item.get(
                            "score",
                            0.0,
                        )
                    ) * 100.0,
                    1,
                ),
                "source": item.get(
                    "source"
                ),
                "evidence": item.get(
                    "validation",
                    {},
                ).get(
                    "supporting_evidence",
                    [],
                ),
                "validation": item.get(
                    "validation"
                ),
            }
        )

    logger.info(
        "SEARCH DEBUG search_id=%s route=%s postgres=%d qdrant_candidates=%d union=%d validated=%d final=%d postgres_s=%.3f qdrant_s=%.3f rerank_s=%.3f validation_s=%.3f total_s=%.3f",
        search_id,
        route,
        len(structured_candidate_ids),
        len(semantic_map),
        len(candidate_ids),
        len(validated_candidates),
        len(results),
        structured_retrieval_seconds,
        semantic_retrieval_seconds,
        rerank_seconds,
        validation_seconds,
        perf_counter() - started_at,
    )
    if trace is not None:
        trace["counts"] = {"structured_candidates": len(structured_candidate_ids),
            "semantic_candidates": len(semantic_candidate_ids), "union": len(candidate_ids),
            "validated": len(validated_candidates), "final": len(results)}
        trace["duration_seconds"] = perf_counter() - started_at
    return results
