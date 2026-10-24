import os
import re
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder

RERANKER_MODEL_NAME = os.getenv(

    "RERANKER_MODEL_NAME",

    "cross-encoder/ms-marco-MiniLM-L-6-v2",

)

RERANKER_BATCH_SIZE = int(
    os.getenv("RERANKER_BATCH_SIZE", "32")
)

SEMANTIC_VALIDATION_MIN_SCORE = float(

    os.getenv(

        "SEMANTIC_VALIDATION_MIN_SCORE",

        "-4.0",

    )

)

ACTIVITY_OBJECT_MIN_SCORE = float(

    os.getenv(

        "ACTIVITY_OBJECT_MIN_SCORE",

        "-4.0",

    )

)

ACTIVITY_ACTION_MIN_SCORE = float(

    os.getenv(

        "ACTIVITY_ACTION_MIN_SCORE",

        "-4.0",

    )

)

# The most important activity gate:

# the requested action and requested object must be supported by the

# SAME evidence unit. This prevents unrelated sentences in one large

# project chunk from being combined into a false positive.

ACTIVITY_JOINT_MIN_SCORE = float(

    os.getenv(

        "ACTIVITY_JOINT_MIN_SCORE",

        "-4.0",

    )

)

ACTIVITY_ACTION_MARGIN = float(

    os.getenv(

        "ACTIVITY_ACTION_MARGIN",

        "0.25",

    )

)

_ACTION_FAMILIES = {

    "BUILD": (

        "build",

        "built",

        "building",

        "develop",

        "developed",

        "developing",

        "implement",

        "implemented",

        "implementing",

        "create",

        "created",

        "creating",

        "engineer",

        "engineered",

        "engineering",

        "design",

        "designed",

        "designing",

        "architect",

        "architected",

        "architecting",

    ),

    "INTEGRATE": (

        "integrate",

        "integrated",

        "integrating",

        "integration",

    ),

    "TEST": (

        "test",

        "tested",

        "testing",

        "qa",

        "quality assurance",

        "validate",

        "validated",

        "validation",

    ),

    "USE": (

        "use",

        "used",

        "using",

        "worked with",

        "work with",

        "utilized",

        "utilised",

    ),

    "SUPPORT": (

        "support",

        "supported",

        "supporting",

        "maintain",

        "maintained",

        "maintenance",

        "monitor",

        "monitored",

        "monitoring",

    ),

}

class RequirementValidation(BaseModel):

    requirement_id: str = ""

    status: Literal[

        "MATCH",

        "NO_MATCH",

        "UNCERTAIN",

    ]

    confidence: float = Field(

        ge=0.0,

        le=1.0,

    )

    reason: str

    evidence_score: float | None = None

class CandidateSemanticValidation(BaseModel):

    matched: bool

    requirements: list[RequirementValidation] = (

        Field(default_factory=list)

    )

    failed_requirements: list[str] = (

        Field(default_factory=list)

    )

_reranker = CrossEncoder(RERANKER_MODEL_NAME)

def _requirement_id(

    requirement: dict,

    index: int,

) -> str:

    return str(

        requirement.get(

            "requirement_id",

            f"REQ_{index}",

        )

    )

def _requirement_query(

    requirement: dict,

) -> str:

    return str(

        requirement.get(

            "evidence_query",

        )

        or requirement.get(

            "value",

            "",

        )

    ).strip()

def _normalize_text(

    value: str,

) -> str:

    return re.sub(

        r"\s+",

        " ",

        value.lower(),

    ).strip()

def _parse_date(value):

    if value is None:

        return None

    if isinstance(value, date):

        return value

    if isinstance(value, str):

        try:

            return date.fromisoformat(

                value[:10]

            )

        except ValueError:

            return None

    return None

def _is_recent_evidence(

    evidence: dict,

    recency_months: int,

) -> bool:

    cutoff = date.today() - timedelta(

        days=recency_months * 30

    )

    start_date = _parse_date(

        evidence.get("start_date")

    )

    end_date = _parse_date(

        evidence.get("end_date")

    )

    if end_date is not None:

        return end_date >= cutoff

    if start_date is not None:

        return (

            start_date <= date.today()

            and date.today() >= cutoff

        )

    return False

def _score_to_confidence(

    score: float,

) -> float:

    """

    Diagnostic confidence-like value.

    This is NOT a probability.

    """

    value = 0.5 + (

        (

            score

            - SEMANTIC_VALIDATION_MIN_SCORE

        )

        / 8.0

    )

    return round(

        max(

            0.0,

            min(

                1.0,

                value,

            ),

        ),

        3,

    )

def _matches_requirement_scope(

    requirement: dict,

    evidence: dict,

) -> bool:

    scope = str(

        requirement.get("scope") or ""

    ).upper()

    if not scope:

        return True

    source = str(

        evidence.get("source") or ""

    ).lower()

    if scope == "PROJECT":

        return (

            evidence.get("project_title") is not None

            or "project" in source

            or evidence.get("chunk_type") in {"project", "projects"}

        )

    if scope == "EXPERIENCE":

        return (

            evidence.get("company") is not None

            or evidence.get("job_title") is not None

            or "experience" in source

            or evidence.get("chunk_type") == "experience"

        )

    return True

def _detect_action_family(

    requirement: dict,

) -> str | None:

    text = _normalize_text(

        str(

            requirement.get("value")

            or requirement.get("evidence_query")

            or ""

        )

    )

    for family, phrases in _ACTION_FAMILIES.items():

        for phrase in phrases:

            if re.search(

                rf"\b{re.escape(phrase)}\b",

                text,

            ):

                return family

    return None

def _extract_activity_object(

    requirement: dict,

) -> str:

    text = _normalize_text(

        str(

            requirement.get("value")

            or requirement.get("evidence_query")

            or ""

        )

    )

    patterns = [

        r"^experience\s+(?:in\s+)?",

        r"^experience\s+(?:with\s+)?",

        r"^hands[- ]on\s+experience\s+(?:in\s+)?",

        r"^worked\s+on\s+",

        r"^worked\s+with\s+",

        r"^working\s+on\s+",

        r"^building\s+",

        r"^built\s+",

        r"^build\s+",

        r"^developing\s+",

        r"^developed\s+",

        r"^develop\s+",

        r"^implementing\s+",

        r"^implemented\s+",

        r"^implement\s+",

        r"^creating\s+",

        r"^created\s+",

        r"^create\s+",

        r"^engineering\s+",

        r"^engineered\s+",

        r"^engineer\s+",

        r"^designing\s+",

        r"^designed\s+",

        r"^design\s+",

        r"^architecting\s+",

        r"^architected\s+",

        r"^architect\s+",

        r"^integrating\s+",

        r"^integrated\s+",

        r"^integrate\s+",

    ]

    result = text

    for pattern in patterns:

        updated = re.sub(

            pattern,

            "",

            result,

            count=1,

        )

        if updated != result:

            result = updated

            break

    return result.strip()

def _action_positive_query(

    requirement: dict,

    action_family: str,

    object_query: str,

) -> str:

    if action_family == "BUILD":

        return (

            "A candidate personally built, developed, implemented, "

            f"engineered, designed, or architected {object_query}."

        )

    if action_family == "INTEGRATE":

        return (

            "A candidate personally integrated or implemented "

            f"{object_query}."

        )

    if action_family == "TEST":

        return (

            "A candidate personally tested or validated "

            f"{object_query}."

        )

    if action_family == "USE":

        return (

            "A candidate personally used or worked with "

            f"{object_query}."

        )

    if action_family == "SUPPORT":

        return (

            "A candidate personally supported or maintained "

            f"{object_query}."

        )

    return (

        "A candidate has direct professional experience with "

        f"{object_query}."

    )

def _action_negative_queries(

    object_query: str,

    action_family: str,

) -> list[str]:

    if action_family != "BUILD":

        return []

    return [

        (

            "A candidate tested or performed quality assurance on "

            f"{object_query} without building it."

        ),

        (

            "A candidate supported, maintained, monitored, or operated "

            f"{object_query} without building it."

        ),

        (

            "A candidate used or worked with "

            f"{object_query} without developing it."

        ),

    ]

def _split_evidence_units(

    text: str,

) -> list[str]:

    """

    Split a retrieved chunk into small evidence units.

    The previous validator scored the whole chunk. That allowed unrelated

    sentences to be combined semantically, e.g.:

        "Architected a CRM platform for Airtel Payment Bank..."

    to be interpreted as:

        "built payment systems"

    We now validate action + object against the same sentence/bullet.

    """

    normalized = str(text or "").strip()

    if not normalized:

        return []

    # Resume/project text is commonly bullet/newline based.

    raw_parts = re.split(

        r"(?:\r?\n)+|[•▪●◦]+|(?:\s+-\s+)",

        normalized,

    )

    units = []

    for part in raw_parts:

        part = re.sub(

            r"\s+",

            " ",

            part,

        ).strip(" \t\r\n-•▪●◦")

        if not part:

            continue

        # Further split long prose into sentence-sized units.

        sentences = re.split(

            r"(?<=[.!?])\s+(?=[A-Z0-9])",

            part,

        )

        for sentence in sentences:

            sentence = re.sub(

                r"\s+",

                " ",

                sentence,

            ).strip()

            if sentence:

                units.append(sentence)

    # De-duplicate while preserving order.

    seen = set()

    unique_units = []

    for unit in units:

        key = _normalize_text(unit)

        if key in seen:

            continue

        seen.add(key)

        unique_units.append(unit)

    # If splitting produced nothing, retain the original chunk.

    return unique_units or [normalized]

def _expand_evidence_units(

    evidence: list[dict],

) -> list[dict]:

    """

    Convert retrieved chunks into sentence/bullet evidence units while

    preserving all original metadata.

    """

    expanded = []

    for item in evidence:

        if not isinstance(item, dict):

            continue

        text = str(

            item.get("text", "")

        ).strip()

        if not text:

            continue

        units = _split_evidence_units(text)

        for unit_index, unit in enumerate(units):

            unit_item = dict(item)

            unit_item["text"] = unit

            unit_item["_evidence_unit_index"] = unit_index

            unit_item["_parent_text"] = text

            expanded.append(unit_item)

    return expanded

def _predict_scores(pairs: list[tuple[str, str]]):
    """Run CrossEncoder inference in one batched call."""
    if not pairs:
        return []

    return _reranker.predict(
        pairs,
        batch_size=RERANKER_BATCH_SIZE,
        show_progress_bar=False,
    )

def _best_cross_encoder_score(
    query: str,
    evidence: list[dict],
) -> tuple[float | None, int | None]:
    if not evidence or not query:
        return None, None

    pairs = [
        (
            query,
            str(item.get("text", "")).strip(),
        )
        for item in evidence
        if str(item.get("text", "")).strip()
    ]

    if not pairs:
        return None, None

    scores = _predict_scores(pairs)

    best_index = max(
        range(len(scores)),
        key=lambda item_index: float(scores[item_index]),
    )

    return (
        float(scores[best_index]),
        best_index,
    )

def _best_scores_for_queries(
    queries: list[str],
    evidence: list[dict],
) -> dict[str, float | None]:
    """Score multiple queries against the same evidence in one model call."""
    if not evidence:
        return {query: None for query in queries if query}

    clean_queries = []
    seen_queries = set()
    for query in queries:
        query = str(query or "").strip()
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        clean_queries.append(query)

    texts = [
        str(item.get("text", "")).strip()
        for item in evidence
        if str(item.get("text", "")).strip()
    ]

    if not clean_queries or not texts:
        return {query: None for query in clean_queries}

    pairs = [
        (query, text)
        for query in clean_queries
        for text in texts
    ]

    scores = _predict_scores(pairs)

    result = {}
    width = len(texts)

    for query_index, query in enumerate(clean_queries):
        start = query_index * width
        end = start + width
        query_scores = scores[start:end]
        result[query] = max(
            (float(score) for score in query_scores),
            default=None,
        )

    return result

def _action_terms(action_family: str) -> tuple[str, ...]:

    """Return action phrases for the requested activity family."""

    return _ACTION_FAMILIES.get(action_family, ())

def _find_action_matches(

    text: str,

    action_family: str,

) -> list[re.Match]:

    """Find action verbs/phrases in evidence text."""

    normalized = _normalize_text(text)

    matches: list[re.Match] = []

    phrases = sorted(

        _action_terms(action_family),

        key=len,

        reverse=True,

    )

    for phrase in phrases:

        matches.extend(

            re.finditer(

                rf"\b{re.escape(phrase)}\b",

                normalized,

            )

        )

    matches.sort(

        key=lambda match: (

            match.start(),

            -(match.end() - match.start()),

        )

    )

    return matches

def _clean_action_object_phrase(value: str) -> str:

    """Normalize an extracted action-object phrase."""

    value = re.sub(r"\s+", " ", value or "").strip(" ,;:-")

    value = re.sub(

        r"^(?:an?|the)\s+",

        "",

        value,

        flags=re.IGNORECASE,

    )

    return value.strip(" ,;:-")

def _extract_action_object_phrases(

    evidence_text: str,

    action_family: str,

) -> list[dict]:

    """

    Deterministically extract the object immediately governed by an action.

    Example:

        "Architected a CME platform for global banking"

        -> action: "architected"

        -> object: "CME platform"

    This prevents "Airtel Payment Bank" from being treated as the object

    of "architected" merely because it occurs later in the same sentence.

    """

    text = _normalize_text(evidence_text)

    if not text:

        return []

    matches = _find_action_matches(text, action_family)

    if not matches:

        return []

    context_prepositions = (

        " for ",

        " using ",

        " with ",

        " through ",

        " via ",

        " across ",

        " within ",

        " during ",

        " under ",

        " by ",

        " to support ",

        " in order to ",

    )

    hard_boundaries = re.compile(r"[.;!?]")

    results: list[dict] = []

    for match in matches:

        remainder = text[match.end():].strip()

        if not remainder:

            continue

        boundary_match = hard_boundaries.search(remainder)

        if boundary_match:

            remainder = remainder[:boundary_match.start()].strip()

        padded = f" {remainder} "

        cut_positions = []

        for preposition in context_prepositions:

            position = padded.find(preposition)

            if position != -1:

                cut_positions.append(position)

        if cut_positions:

            remainder = padded[1:min(cut_positions)].strip()

        # Stop before a second known action joined by "and".

        for other_family, phrases in _ACTION_FAMILIES.items():

            if other_family == action_family:

                continue

            found_second_action = False

            for phrase in sorted(phrases, key=len, reverse=True):

                second_action = re.search(

                    rf"\band\s+{re.escape(phrase)}\b",

                    remainder,

                )

                if second_action:

                    remainder = remainder[

                        :second_action.start()

                    ].strip()

                    found_second_action = True

                    break

            if found_second_action:

                break

        object_phrase = _clean_action_object_phrase(remainder)

        if not object_phrase:

            continue

        # A direct object should remain local to the action.

        words = object_phrase.split()

        if len(words) > 20:

            object_phrase = " ".join(words[:20])

        results.append(

            {

                "action": match.group(0),

                "object": object_phrase,

            }

        )

    seen: set[tuple[str, str]] = set()

    unique: list[dict] = []

    for item in results:

        key = (

            str(item["action"]),

            str(item["object"]),

        )

        if key in seen:

            continue

        seen.add(key)

        unique.append(item)

    return unique

def _object_semantic_score(
    requested_object: str,
    extracted_objects: list[str],
) -> float | None:
    """Score requested object against extracted objects in one batch."""
    if not requested_object or not extracted_objects:
        return None

    pairs = [
        (
            requested_object,
            str(extracted_object).strip(),
        )
        for extracted_object in extracted_objects
        if str(extracted_object).strip()
    ]

    if not pairs:
        return None

    scores = _predict_scores(pairs)
    return max(float(score) for score in scores)

def _activity_validation(
    requirement: dict,
    usable_evidence: list[dict],
) -> tuple[str, float, str, float | None]:
    """
    Validate an ACTIVITY requirement while minimizing CrossEncoder calls.

    All evidence-level queries needed for the activity decision are scored
    together in one batched inference call. Extracted action-object pairs are
    scored in one additional batch. This preserves the qualification logic
    while avoiding repeated CrossEncoder inference for the same candidate.
    """
    action_family = _detect_action_family(requirement)
    object_query = _extract_activity_object(requirement)
    generic_query = _requirement_query(requirement)

    if action_family is None:
        score, _ = _best_cross_encoder_score(
            generic_query,
            usable_evidence,
        )

        if score is None:
            return (
                "UNCERTAIN",
                0.0,
                "No usable evidence was available.",
                None,
            )

        if score >= SEMANTIC_VALIDATION_MIN_SCORE:
            return (
                "MATCH",
                _score_to_confidence(score),
                "The strongest eligible evidence is semantically relevant to the requested requirement.",
                score,
            )

        return (
            "NO_MATCH",
            _score_to_confidence(score),
            "The strongest eligible evidence is too weakly related to the requested requirement.",
            score,
        )

    expanded_evidence = _expand_evidence_units(usable_evidence)

    if not expanded_evidence:
        return (
            "UNCERTAIN",
            0.0,
            "No usable sentence-level evidence was available.",
            None,
        )

    positive_query = _action_positive_query(
        requirement,
        action_family,
        object_query,
    )

    negative_queries = _action_negative_queries(
        object_query,
        action_family,
    )

    evidence_queries = [
        generic_query,
        object_query,
        positive_query,
        *negative_queries,
    ]

    evidence_scores = _best_scores_for_queries(
        evidence_queries,
        expanded_evidence,
    )

    generic_score = evidence_scores.get(generic_query)
    object_score = evidence_scores.get(object_query)
    action_score = evidence_scores.get(positive_query)

    if object_score is None or action_score is None:
        return (
            "UNCERTAIN",
            0.0,
            "No usable evidence was available.",
            generic_score,
        )

    action_object_candidates: list[dict] = []

    for evidence_index, evidence_item in enumerate(expanded_evidence):
        evidence_text = str(
            evidence_item.get("text", "")
        ).strip()

        if not evidence_text:
            continue

        extracted = _extract_action_object_phrases(
            evidence_text,
            action_family,
        )

        for item in extracted:
            action_object_candidates.append(
                {
                    "evidence_index": evidence_index,
                    "evidence": evidence_item,
                    "action": item["action"],
                    "object": item["object"],
                }
            )

    if not action_object_candidates:
        return (
            "NO_MATCH",
            _score_to_confidence(min(object_score, action_score)),
            "The evidence contains no explicit action phrase whose direct object can be identified for the requested activity.",
            generic_score,
        )

    pair_objects = [
        str(item["object"]).strip()
        for item in action_object_candidates
        if str(item["object"]).strip()
    ]

    pair_scores = _predict_scores([
        (object_query, object_text)
        for object_text in pair_objects
    ])

    best_pair = None
    best_pair_score = None
    score_index = 0

    for item in action_object_candidates:
        object_text = str(item["object"]).strip()
        if not object_text:
            continue

        pair_score = float(pair_scores[score_index])
        score_index += 1

        if best_pair_score is None or pair_score > best_pair_score:
            best_pair_score = pair_score
            best_pair = item

    if best_pair is None or best_pair_score is None:
        return (
            "NO_MATCH",
            _score_to_confidence(min(object_score, action_score)),
            "No extracted action-object pair provides sufficient semantic support for the requested object.",
            generic_score,
        )

    action_object_ok = (
        best_pair_score >= SEMANTIC_VALIDATION_MIN_SCORE
    )

    strongest_negative = None
    for negative_query in negative_queries:
        negative_score = evidence_scores.get(negative_query)
        if (
            negative_score is not None
            and (
                strongest_negative is None
                or negative_score > strongest_negative
            )
        ):
            strongest_negative = negative_score

    competing_activity = (
        action_family == "BUILD"
        and strongest_negative is not None
        and strongest_negative
        >= best_pair_score + ACTIVITY_ACTION_MARGIN
    )

    if action_object_ok and not competing_activity:
        combined_score = (
            0.60 * best_pair_score
            + 0.20 * action_score
            + 0.20 * object_score
        )

        action_text = str(best_pair["action"])
        object_text = str(best_pair["object"])

        return (
            "MATCH",
            _score_to_confidence(combined_score),
            (
                "The evidence explicitly contains the requested activity "
                f"action '{action_text}' applied to the extracted object "
                f"'{object_text}', which is semantically compatible with "
                f"the requested object '{object_query}'."
            ),
            generic_score,
        )

    if competing_activity:
        return (
            "NO_MATCH",
            _score_to_confidence(
                min(best_pair_score, object_score)
            ),
            (
                "The requested object is present in activity-related "
                "evidence, but the strongest competing activity is better "
                "explained by testing, support, monitoring, or usage."
            ),
            generic_score,
        )

    return (
        "NO_MATCH",
        _score_to_confidence(
            min(best_pair_score, action_score, object_score)
        ),
        (
            "The candidate performed a recognized activity, but the "
            "direct object of that activity is not sufficiently compatible "
            "with the requested object."
        ),
        generic_score,
    )

def _validate_requirement(
    requirement: dict,
    index: int,
    evidence: list[dict],
) -> RequirementValidation:
    requirement_id = _requirement_id(
        requirement,
        index,
    )

    query = _requirement_query(requirement)

    if not query:
        return RequirementValidation(
            requirement_id=requirement_id,
            status="UNCERTAIN",
            confidence=0.0,
            reason="The semantic requirement has no usable evidence query.",
            evidence_score=None,
        )

    usable_evidence = []

    for item in evidence:
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()

        if not text:
            continue

        if not _matches_requirement_scope(requirement, item):
            continue

        usable_evidence.append(item)

    if not usable_evidence:
        return RequirementValidation(
            requirement_id=requirement_id,
            status="NO_MATCH",
            confidence=0.0,
            reason="No usable evidence was retrieved for this requirement.",
            evidence_score=None,
        )

    recency_months = requirement.get("recency_months")

    if recency_months is not None:
        recent_evidence = [
            item
            for item in usable_evidence
            if _is_recent_evidence(
                item,
                int(recency_months),
            )
        ]

        if not recent_evidence:
            return RequirementValidation(
                requirement_id=requirement_id,
                status="UNCERTAIN",
                confidence=0.0,
                reason=(
                    "The retrieved evidence does not contain a date that "
                    "can prove the requested recency window."
                ),
                evidence_score=None,
            )

        usable_evidence = recent_evidence

    requirement_type = str(
        requirement.get("type") or ""
    ).upper()

    if requirement_type == "ACTIVITY":
        (
            status,
            confidence,
            reason,
            generic_score,
        ) = _activity_validation(
            requirement,
            usable_evidence,
        )

        return RequirementValidation(
            requirement_id=requirement_id,
            status=status,
            confidence=confidence,
            reason=reason,
            evidence_score=(
                round(generic_score, 6)
                if generic_score is not None
                else None
            ),
        )

    best_score, _ = _best_cross_encoder_score(
        query,
        usable_evidence,
    )

    if best_score is None:
        return RequirementValidation(
            requirement_id=requirement_id,
            status="UNCERTAIN",
            confidence=0.0,
            reason="No usable evidence was available.",
            evidence_score=None,
        )

    if best_score >= SEMANTIC_VALIDATION_MIN_SCORE:
        return RequirementValidation(
            requirement_id=requirement_id,
            status="MATCH",
            confidence=_score_to_confidence(best_score),
            reason=(
                "The strongest eligible evidence is semantically relevant "
                "to the requested requirement above the validation "
                "threshold."
            ),
            evidence_score=round(best_score, 6),
        )

    return RequirementValidation(
        requirement_id=requirement_id,
        status="NO_MATCH",
        confidence=_score_to_confidence(best_score),
        reason=(
            "The retrieved evidence is too weakly related to the requested "
            "requirement to qualify as a match."
        ),
        evidence_score=round(best_score, 6),
    )

def validate_semantic_requirements(

    requirements: list[dict] | None,

    evidence: list[dict],

) -> dict:

    """

    Validate semantic recruiter requirements without an LLM.

    Retrieval and CrossEncoder reranking identify potentially relevant

    evidence. This stage independently qualifies the evidence.

    For ACTIVITY requirements, qualification requires:

      1. object/domain relevance,

      2. action relevance,

      3. action + object relevance in the SAME sentence/bullet,

      4. no stronger competing activity for BUILD requirements.

    Required requirements must be MATCH.

    Optional requirements may remain NO_MATCH or UNCERTAIN.

    """

    semantic_requirements = []

    for requirement in requirements or []:

        if not isinstance(

            requirement,

            dict,

        ):

            continue

        if requirement.get("type") not in {

            "ACTIVITY",

            "INDUSTRY",

            "OTHER",

        }:

            continue

        semantic_requirements.append(

            requirement

        )

    if not semantic_requirements:

        return {

            "matched": True,

            "requirements": [],

            "failed_requirements": [],

        }

    validation_results = []

    failed_requirements = []

    for index, requirement in enumerate(

        semantic_requirements,

        start=1,

    ):

        result = _validate_requirement(

            requirement=requirement,

            index=index,

            evidence=evidence,

        )

        validation_results.append(

            result.model_dump()

        )

        if (

            requirement.get(

                "required",

                True,

            )

            and result.status != "MATCH"

        ):

            failed_requirements.append(

                requirement.get(

                    "value",

                    "",

                )

            )

    return {

        "matched": not bool(

            failed_requirements

        ),

        "requirements": validation_results,

        "failed_requirements": failed_requirements,

    }
