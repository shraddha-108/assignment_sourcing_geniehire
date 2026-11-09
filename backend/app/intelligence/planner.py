"""Capability-based execution planning for recruiter requirement graphs."""

from collections import defaultdict, deque

from app.search.schema import SearchRequirement


CAPABILITY_STAGE = {
    "structured_candidate_lookup": "structured_filter",
    "structured_experience_lookup": "structured_filter",
    "semantic_evidence_retrieval": "semantic_retrieval",
    "relationship_resolution": "relationship_resolution",
    "temporal_validation": "temporal_validation",
    "evidence_validation": "evidence_validation",
}

STAGE_DEPENDENCIES = {
    "structured_filter": set(),
    "semantic_retrieval": set(),
    "chunk_reranking": {"semantic_retrieval"},
    "candidate_consolidation": {"chunk_reranking"},
    "candidate_semantic_validation": {"candidate_consolidation"},
    "relationship_resolution": set(),
    "temporal_validation": set(),
    "evidence_validation": set(),
    "qualification": set(),
    "ranking": {"qualification"},
}


def semantic_candidate_scope(
    hard_structured_requirements: bool,
    structured_candidate_ids: list[int],
) -> list[int] | None:
    """None means unscoped; an empty list means hard filtering found none."""
    return structured_candidate_ids if hard_structured_requirements else None


def default_capabilities(requirement: SearchRequirement) -> list[str]:
    """Provide generic capability defaults when a parser omits them."""
    if requirement.capabilities:
        return list(dict.fromkeys(requirement.capabilities))
    by_type = {
        "STRUCTURED": ["structured_candidate_lookup"],
        "SEMANTIC": ["semantic_evidence_retrieval", "evidence_validation"],
        "TEMPORAL": ["temporal_validation", "evidence_validation"],
        "RELATIONAL": ["relationship_resolution", "evidence_validation"],
        "COMPOSITE": ["evidence_validation"],
    }
    return by_type.get(requirement.type, ["evidence_validation"])


def build_execution_plan(
    requirements: list[SearchRequirement],
) -> dict:
    """Topologically order requirement work and expose its rationale."""
    by_id = {requirement.id: requirement for requirement in requirements}
    if len(by_id) != len(requirements):
        raise ValueError("Requirement IDs must be unique")
    for requirement in requirements:
        unknown = set(requirement.dependencies) - set(by_id)
        if unknown:
            raise ValueError(
                f"Requirement {requirement.id} references unknown dependencies: {sorted(unknown)}"
            )

    dependents: dict[str, list[str]] = defaultdict(list)
    indegree = {requirement.id: 0 for requirement in requirements}
    for requirement in requirements:
        for dependency in requirement.dependencies:
            dependents[dependency].append(requirement.id)
            indegree[requirement.id] += 1

    queue = deque(
        requirement.id for requirement in requirements if indegree[requirement.id] == 0
    )
    ordered_ids = []
    while queue:
        requirement_id = queue.popleft()
        ordered_ids.append(requirement_id)
        for dependent in dependents[requirement_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(ordered_ids) != len(requirements):
        raise ValueError("Requirement dependencies contain a cycle")

    stage_requirements: dict[str, list[str]] = defaultdict(list)
    stage_reasons: dict[str, list[str]] = defaultdict(list)
    for requirement_id in ordered_ids:
        requirement = by_id[requirement_id]
        for capability in default_capabilities(requirement):
            stage = CAPABILITY_STAGE.get(capability)
            if stage is None:
                # Unknown capabilities remain visible for future executors,
                # but do not trigger an unsupported operation.
                stage = f"capability:{capability}"
            stage_requirements[stage].append(requirement_id)
            stage_reasons[stage].append(
                f"{requirement_id} requires {capability}"
            )

    stages = set(stage_requirements)
    if "semantic_retrieval" in stages:
        stages.update({
            "chunk_reranking",
            "candidate_consolidation",
            "candidate_semantic_validation",
        })
        stage_reasons["chunk_reranking"].append(
            "CrossEncoder ranks retrieved chunks against each semantic requirement"
        )
        stage_reasons["candidate_consolidation"].append(
            "Keep the strongest distinct chunks for each candidate and requirement"
        )
        stage_reasons["candidate_semantic_validation"].append(
            "CrossEncoder evaluates each candidate's consolidated evidence against the requirement"
        )
        stages.add("evidence_validation")
        stage_reasons["evidence_validation"].append(
            "Semantic requirements must be checked against retrieved resume evidence"
        )
    if stages.intersection({
        "structured_filter", "semantic_retrieval", "evidence_validation",
        "candidate_semantic_validation", "temporal_validation", "relationship_resolution",
    }):
        stages.add("qualification")
        stage_reasons["qualification"].append(
            "Apply all mandatory requirement outcomes to the candidate"
        )
    stages.add("ranking")

    dependencies = {stage: set(STAGE_DEPENDENCIES.get(stage, set())) & stages for stage in stages}
    # First identify relevant evidence. Temporal and relational checks then
    # consume those resolved sources, and qualification applies all outcomes.
    if "evidence_validation" in stages:
        for source_stage in (
            "structured_filter", "semantic_retrieval", "candidate_semantic_validation"
        ):
            if source_stage in stages:
                dependencies["evidence_validation"].add(source_stage)
    for dependent_stage in ("temporal_validation", "relationship_resolution"):
        if dependent_stage in stages:
            if "evidence_validation" in stages:
                dependencies[dependent_stage].add("evidence_validation")
            else:
                for source_stage in ("structured_filter", "semantic_retrieval"):
                    if source_stage in stages:
                        dependencies[dependent_stage].add(source_stage)
    if "qualification" in stages:
        for prerequisite in (
            "structured_filter", "semantic_retrieval", "evidence_validation",
            "candidate_semantic_validation", "temporal_validation", "relationship_resolution",
        ):
            if prerequisite in stages:
                dependencies["qualification"].add(prerequisite)
    # Hard structured constraints constrain candidate discovery, so run the
    # structured filter before semantic retrieval when both are present.
    if "structured_filter" in stages and "semantic_retrieval" in stages:
        dependencies["semantic_retrieval"].add("structured_filter")
        stage_reasons["semantic_retrieval"].append(
            "Hard structured requirements scope semantic retrieval to eligible candidates"
        )

    # Dependencies in the requirement graph become operation dependencies.
    for requirement in requirements:
        requirement_stages = [
            CAPABILITY_STAGE.get(capability, f"capability:{capability}")
            for capability in default_capabilities(requirement)
        ]
        for dependency_id in requirement.dependencies:
            dependency = by_id[dependency_id]
            dependency_stages = [
                CAPABILITY_STAGE.get(capability, f"capability:{capability}")
                for capability in default_capabilities(dependency)
                if CAPABILITY_STAGE.get(capability, f"capability:{capability}")
                not in {"qualification", "ranking"}
            ]
            for stage in requirement_stages:
                for dependency_stage in dependency_stages:
                    if stage != dependency_stage and dependency_stage in stages:
                        dependencies[stage].add(dependency_stage)

    # Kahn ordering over operation dependencies.
    stage_indegree = {stage: len(dependencies[stage]) for stage in stages}
    stage_dependents: dict[str, list[str]] = defaultdict(list)
    for stage, deps in dependencies.items():
        for dep in deps:
            stage_dependents[dep].append(stage)
    stage_queue = deque(sorted(stage for stage, degree in stage_indegree.items() if degree == 0))
    ordered_stages = []
    while stage_queue:
        stage = stage_queue.popleft()
        ordered_stages.append(stage)
        for dependent in stage_dependents[stage]:
            stage_indegree[dependent] -= 1
            if stage_indegree[dependent] == 0:
                stage_queue.append(dependent)
    if len(ordered_stages) != len(stages):
        raise ValueError("Capability dependencies create an execution cycle")

    explanation = [
        f"{requirement.id} ({requirement.type.lower()}) is resolved using "
        f"{', '.join(default_capabilities(requirement))}."
        + (
            f" It depends on {', '.join(requirement.dependencies)}."
            if requirement.dependencies else ""
        )
        for requirement in requirements
    ]
    return {
        "requirement_order": ordered_ids,
        "stages": [
            {
                "stage": stage,
                "requirement_ids": list(dict.fromkeys(stage_requirements.get(stage, []))),
                "depends_on": sorted(dependencies[stage]),
                "reasons": list(dict.fromkeys(stage_reasons.get(stage, []))),
            }
            for stage in ordered_stages
        ],
        "explanation": explanation,
    }
