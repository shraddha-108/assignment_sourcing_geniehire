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



    matched_evidence: dict | None = None



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



    """Build the semantic query while preserving an explicit target."""



    base = str(



        requirement.get("evidence_query")



        or requirement.get("value", "")



    ).strip()



    target = str(requirement.get("target") or "").strip()



    if not target:



        return base



    if target.lower() in _normalize_text(base).split():



        return base



    return f"{base} {target}".strip()



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



            or evidence.get("chunk_type") == "project"



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



    # Strip an explicit action phrase when the requirement starts with one,



    # then keep the main object before common context prepositions.



    action_family = _detect_action_family(requirement)



    if action_family:



        for phrase in sorted(_action_terms(action_family), key=len, reverse=True):



            result = re.sub(



                rf"^{re.escape(phrase)}\s+",



                "",



                result,



                count=1,



                flags=re.IGNORECASE,



            )



            if result != text:



                break



    for preposition in (" in ", " using ", " with ", " via ", " through ", " for "):



        position = result.find(preposition)



        if position > 0:



            result = result[:position].strip()



            break



    return result.strip()



def _action_positive_query(



    requirement: dict,



    action_family: str,



    object_query: str,



) -> str:



    target = str(requirement.get("target") or "").strip()



    target_suffix = f" using or involving {target}" if target else ""



    if action_family == "BUILD":



        return (



            "A candidate personally built, developed, implemented, "



            f"engineered, designed, or architected {object_query}"



            f"{target_suffix}."



        )



    if action_family == "INTEGRATE":



        return (



            "A candidate personally integrated or implemented "



            f"{object_query}{target_suffix}."



        )



    if action_family == "TEST":



        return (



            "A candidate personally tested or validated "



            f"{object_query}{target_suffix}."



        )



    if action_family == "USE":



        return (



            "A candidate personally used or worked with "



            f"{object_query}{target_suffix}."



        )



    if action_family == "SUPPORT":



        return (



            "A candidate personally supported or maintained "



            f"{object_query}{target_suffix}."



        )



    return (



        "A candidate has direct professional experience with "



        f"{object_query}{target_suffix}."



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

        evidence_group_id = len(expanded)



        for unit_index, unit in enumerate(units):

            unit_item = dict(item)

            unit_item["text"] = unit

            unit_item["_evidence_unit_index"] = unit_index

            unit_item["_parent_text"] = text

            unit_item["_evidence_group_id"] = evidence_group_id

            expanded.append(unit_item)



    return expanded



def _build_local_evidence_context(

    evidence_units: list[dict],

    evidence_index: int,

    window: int = 1,

) -> str:

    """Build bounded context around one evidence unit from the same chunk."""

    if evidence_index < 0 or evidence_index >= len(evidence_units):

        return ""



    current = evidence_units[evidence_index]

    group_id = current.get("_evidence_group_id")

    current_unit_index = current.get("_evidence_unit_index")



    selected: list[tuple[int, str]] = []

    for item in evidence_units:

        if item.get("_evidence_group_id") != group_id:

            continue

        unit_index = item.get("_evidence_unit_index")

        if not isinstance(unit_index, int) or not isinstance(current_unit_index, int):

            continue

        if abs(unit_index - current_unit_index) > window:

            continue

        text = str(item.get("text") or "").strip()

        if text:

            selected.append((unit_index, text))



    if not selected:

        return str(current.get("text") or "").strip()



    selected.sort(key=lambda item: item[0])

    return " ".join(text for _, text in selected).strip()



def _best_cross_encoder_score(



    query: str,



    evidence: list[dict],



) -> tuple[float | None, int | None]:



    if not evidence:



        return None, None



    pairs = [



        (



            query,



            str(



                item.get(



                    "text",



                    "",



                )



            ).strip(),



        )



        for item in evidence



    ]



    scores = _reranker.predict(pairs)



    best_index = max(



        range(len(scores)),



        key=lambda item_index: float(



            scores[item_index]



        ),



    )



    return (



        float(scores[best_index]),



        best_index,



    )



def _find_highlight_spans(



    text: str,



    phrases: list[str] | tuple[str, ...] | None,



) -> list[dict]:



    """Return exact character spans for phrases that occur in evidence."""



    if not text or not phrases:



        return []



    spans = []



    seen = set()



    for phrase in phrases:



        phrase = str(phrase or "").strip()



        if not phrase or len(phrase) < 2:



            continue



        for match in re.finditer(



            re.escape(phrase),



            text,



            flags=re.IGNORECASE,



        ):



            key = (match.start(), match.end())



            if key in seen:



                continue



            seen.add(key)



            spans.append(



                {



                    "start": match.start(),



                    "end": match.end(),



                    "text": text[match.start():match.end()],



                }



            )



    spans.sort(key=lambda item: (item["start"], item["end"]))



    merged = []



    for span in spans:



        if merged and span["start"] <= merged[-1]["end"]:



            if span["end"] > merged[-1]["end"]:



                merged[-1]["end"] = span["end"]



                merged[-1]["text"] = text[



                    merged[-1]["start"]:



                    merged[-1]["end"]



                ]



            continue



        merged.append(dict(span))



    return merged



def _highlight_query_phrases(query: str) -> list[str]:



    """Build conservative lexical phrases for generic evidence highlighting."""



    query = str(query or "").strip()



    if not query:



        return []



    stop_words = {



        "a", "an", "and", "are", "be", "candidate", "candidates",



        "experience", "experienced", "find", "for", "have", "has",



        "in", "of", "on", "the", "to", "with", "who", "that",



        "using", "used", "use", "working", "worked",



    }



    tokens = re.findall(



        r"[A-Za-z0-9][A-Za-z0-9+#._/-]{1,}",



        query,



    )



    phrases = [query]



    phrases.extend(



        token



        for token in tokens



        if token.lower() not in stop_words



    )



    return list(dict.fromkeys(phrases))



def _build_evidence_payload(



    evidence: dict | None,



    phrases: list[str] | tuple[str, ...] | None = None,



) -> dict | None:



    """Create recruiter-facing evidence with exact highlight positions."""



    if not isinstance(evidence, dict):



        return None



    text = str(evidence.get("text", "")).strip()



    if not text:



        return None



    return {



        "source": evidence.get("source") or evidence.get("section") or evidence.get("chunk_type") or "unknown",



        "text": text,



        "retrieval_score": round(float(evidence.get("retrieval_score", 0)), 6),



        "reranker_score": round(float(evidence.get("reranker_score", 0)), 6),



        "company": evidence.get("company"),



        "job_title": evidence.get("job_title"),



        "start_date": evidence.get("start_date"),



        "end_date": evidence.get("end_date"),



        "project_title": evidence.get("project_title"),



        "highlight_spans": _find_highlight_spans(text, phrases or []),



    }



def _action_terms(action_family: str) -> tuple[str, ...]:



    """Return action phrases for the requested activity family."""



    return _ACTION_FAMILIES.get(action_family, ())



_AMBIGUOUS_BUILD_ACTION_TERMS = {



    "engineer",



    "engineering",



    "design",



    "architect",



}



_BUILD_NOUN_PRECEDERS = {



    "software",



    "product",



    "products",



    "solution",



    "solutions",



    "system",



    "systems",



    "technical",



    "technology",



    "technologies",



    "data",



    "cloud",



    "network",



    "platform",



    "platforms",



}



_BUILD_NOUN_FOLLOWERS = {



    "leadership",



    "manager",



    "management",



    "director",



    "directors",



    "team",



    "teams",



    "role",



    "roles",



    "department",



    "departments",



    "function",



    "functions",



    "organization",



    "organisations",



    "organization",



}



def _is_probable_action_match(



    normalized: str,



    match: re.Match,



    phrase: str,



    action_family: str,



) -> bool:



    """Reject obvious noun/role uses of ambiguous BUILD terms."""



    if action_family != "BUILD" or phrase.lower() not in _AMBIGUOUS_BUILD_ACTION_TERMS:



        return True



    before = normalized[:match.start()].strip()



    after = normalized[match.end():].strip()



    previous_word = before.split()[-1].lower() if before else ""



    next_word = after.split()[0].lower() if after else ""



    if previous_word in _BUILD_NOUN_PRECEDERS:



        return False



    if next_word in _BUILD_NOUN_FOLLOWERS:



        return False



    # A role/title pattern such as "senior software engineer" is not an



    # activity performed by the candidate.



    if phrase.lower() == "engineer" and previous_word in {



        "senior",



        "lead",



        "principal",



        "staff",



        "chief",



        "junior",



    }:



        return False



    if phrase.lower() == "architect" and previous_word in {



        "solution",



        "enterprise",



        "technical",



        "software",



        "cloud",



        "data",



    }:



        return False



    return True



def _find_action_matches(



    text: str,



    action_family: str,



) -> list[re.Match]:



    """Find action phrases while rejecting obvious noun/title matches."""



    normalized = _normalize_text(text)



    matches: list[re.Match] = []



    phrases = sorted(



        _action_terms(action_family),



        key=len,



        reverse=True,



    )



    for phrase in phrases:



        for match in re.finditer(



            rf"\b{re.escape(phrase)}\b",



            normalized,



        ):



            if _is_probable_action_match(



                normalized,



                match,



                phrase,



                action_family,



            ):



                matches.append(match)



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



        " in ",



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



    """Score the requested object against extracted action objects."""



    if not requested_object or not extracted_objects:



        return None



    pairs = [



        (



            requested_object,



            extracted_object,



        )



        for extracted_object in extracted_objects



        if extracted_object.strip()



    ]



    if not pairs:



        return None



    scores = _reranker.predict(pairs)



    return max(float(score) for score in scores)



def _target_tokens(value: str) -> list[str]:
    """Return meaningful normalized tokens for a semantic target."""
    normalized = _normalize_text(value)
    return re.findall(r"[a-z0-9]+(?:[+#.]?[a-z0-9]+)*[+#]?", normalized)


def _target_is_lexically_supported(target: str, evidence_text: str) -> bool:
    """Check whether the target is explicitly represented in one evidence unit.

    This is deliberately generic. It handles phrases, hyphenated compounds,
    and common technical forms such as C#, React.js, AI-powered, and
    machine-learning without naming particular technologies in the logic.
    """
    target_tokens = _target_tokens(target)
    evidence_tokens = set(_target_tokens(evidence_text))
    if not target_tokens or not evidence_tokens:
        return False

    # A single-token target is satisfied by an explicit token occurrence.
    if len(target_tokens) == 1:
        return target_tokens[0] in evidence_tokens

    # Multi-token targets are satisfied when every meaningful target token is
    # explicitly present in the same atomic evidence unit.
    return all(token in evidence_tokens for token in target_tokens)


_TARGET_RELATION_MARKERS = (
    " using ",
    " with ",
    " via ",
    " through ",
    " leveraging ",
    " leverages ",
    " leveraged ",
    " powered by ",
    " based on ",
    " built on ",
    " incorporating ",
    " integrated with ",
    " integrated into ",
    " for ",
)


def _contains_target_tokens(target: str, text: str) -> bool:
    """Return True when all meaningful target tokens occur in text."""
    target_tokens = _target_tokens(target)
    evidence_tokens = set(_target_tokens(text))
    if not target_tokens or not evidence_tokens:
        return False
    return all(token in evidence_tokens for token in target_tokens)


def _target_is_attached_to_action_object(
    target: str,
    evidence_text: str,
    action: str,
    object_phrase: str,
) -> bool:
    """Check whether the requested target is attached to the action/object.

    A target appearing anywhere in the same evidence sentence is not enough.
    It must either be part of the extracted object itself (for example,
    ``AI-powered applications``) or occur in the first explicit relation
    clause attached to that object (for example, ``products using AI``).

    This is intentionally technology-agnostic. It prevents unrelated clauses
    such as ``building web applications ... AI-powered development tools``
    from satisfying ``built products with AI`` while preserving normal
    constructions such as ``built products using AI``.
    """
    target = str(target or "").strip()
    evidence_text = _normalize_text(evidence_text)
    action = str(action or "").strip()
    object_phrase = str(object_phrase or "").strip()

    if not target or not evidence_text or not action or not object_phrase:
        return False

    if _contains_target_tokens(target, object_phrase):
        return True

    action_match = re.search(
        rf"\b{re.escape(action)}\b",
        evidence_text,
        flags=re.IGNORECASE,
    )
    if not action_match:
        return False

    object_start = evidence_text.lower().find(
        object_phrase.lower(),
        action_match.end(),
    )
    if object_start == -1:
        return False

    object_end = object_start + len(object_phrase)
    remainder = evidence_text[object_end:]

    # Stay inside this sentence/bullet.
    boundary = re.search(r"[.;!?]", remainder)
    if boundary:
        remainder = remainder[:boundary.start()]

    # A second candidate-performed action starts a new relationship. Do not
    # borrow its target.
    action_matches = []
    for family in _ACTION_FAMILIES:
        for phrase in _action_terms(family):
            found = re.search(
                rf"\b{re.escape(phrase)}\b",
                remainder,
                flags=re.IGNORECASE,
            )
            if found:
                action_matches.append(found.start())
    if action_matches:
        remainder = remainder[:min(action_matches)].strip()

    padded = f" {remainder.lower()} "
    marker_positions = []
    for marker in _TARGET_RELATION_MARKERS:
        position = padded.find(marker)
        if position != -1:
            marker_positions.append(position)

    if not marker_positions:
        return False

    first_marker = min(marker_positions)
    relation = padded[first_marker + 1:].strip()

    # Do not let a later independent conjunction introduce a new relationship.
    relation = re.split(r"\s+and\s+", relation, maxsplit=1)[0].strip()

    return _contains_target_tokens(target, relation)


def _activity_validation(
    requirement: dict,
    usable_evidence: list[dict],
) -> tuple[str, float, str, dict | None, float | None]:
    """Qualify an activity using one atomic evidence unit at a time.

    The key invariant is that a target-bearing activity is qualified only when
    action + object + target are supported by the SAME atomic evidence unit.
    Neighboring sentences/bullets are never combined to manufacture a
    relationship.

    Semantic scoring is still used so that valid paraphrases work, while the
    atomic-unit constraint prevents a generic mention elsewhere in the resume
    from satisfying the relationship.
    """
    action_family = _detect_action_family(requirement)
    object_query = _extract_activity_object(requirement)
    target_query = str(requirement.get("target") or "").strip()
    generic_query = _requirement_query(requirement)

    if not usable_evidence:
        return "UNCERTAIN", 0.0, "No usable evidence was available.", None, None

    if action_family is None:
        score, best_index = _best_cross_encoder_score(
            generic_query,
            usable_evidence,
        )
        if score is None or best_index is None:
            return "UNCERTAIN", 0.0, "No usable evidence was available.", None, None
        if score >= SEMANTIC_VALIDATION_MIN_SCORE:
            return (
                "MATCH",
                _score_to_confidence(score),
                "The strongest eligible evidence is semantically relevant to the requested requirement.",
                _build_evidence_payload(
                    usable_evidence[best_index],
                    _highlight_query_phrases(generic_query),
                ),
                round(score, 6),
            )
        return (
            "NO_MATCH",
            _score_to_confidence(score),
            "The strongest eligible evidence is too weakly related to the requested requirement.",
            None,
            round(score, 6),
        )

    if not object_query:
        score, best_index = _best_cross_encoder_score(
            generic_query,
            usable_evidence,
        )
        if (
            score is not None
            and best_index is not None
            and score >= SEMANTIC_VALIDATION_MIN_SCORE
        ):
            return (
                "MATCH",
                _score_to_confidence(score),
                "The evidence is strongly relevant to the requested activity, but no narrower object could be extracted.",
                _build_evidence_payload(
                    usable_evidence[best_index],
                    _highlight_query_phrases(generic_query),
                ),
                round(score, 6),
            )
        return (
            "UNCERTAIN",
            _score_to_confidence(score) if score is not None else 0.0,
            "The activity requirement does not contain enough object information for reliable qualification.",
            None,
            round(score, 6) if score is not None else None,
        )

    positive_query = _action_positive_query(
        requirement,
        action_family,
        object_query,
    )

    expanded_evidence = _expand_evidence_units(usable_evidence)
    if not expanded_evidence:
        return (
            "UNCERTAIN",
            0.0,
            "No usable sentence-level evidence was available.",
            None,
            None,
        )

    action_object_candidates: list[dict] = []
    for evidence_index, evidence_item in enumerate(expanded_evidence):
        evidence_text = str(evidence_item.get("text", "")).strip()
        if not evidence_text:
            continue

        extracted = _extract_action_object_phrases(
            evidence_text,
            action_family,
        )
        for extracted_item in extracted:
            action_object_candidates.append(
                {
                    "evidence_index": evidence_index,
                    "evidence": evidence_item,
                    "action": extracted_item["action"],
                    "object": extracted_item["object"],
                }
            )

    if not action_object_candidates:
        return (
            "NO_MATCH",
            0.0,
            "The evidence contains no explicit candidate-performed action whose direct object can be identified for the requested activity.",
            None,
            None,
        )

    if not target_query:
        # Targetless activities retain the established action/object behavior.
        object_pairs = [
            (object_query, str(item["object"]).strip())
            for item in action_object_candidates
            if str(item["object"]).strip()
        ]
        object_scores = _reranker.predict(object_pairs) if object_pairs else []

        relationship_pairs = [
            (
                positive_query,
                str(item["evidence"].get("text", "")).strip(),
            )
            for item in action_object_candidates
        ]
        relationship_scores = (
            _reranker.predict(relationship_pairs)
            if relationship_pairs
            else []
        )

        best_pair = None
        best_score = None
        for index, item in enumerate(action_object_candidates):
            object_score = (
                float(object_scores[index])
                if index < len(object_scores)
                else None
            )
            activity_score = (
                float(relationship_scores[index])
                if index < len(relationship_scores)
                else None
            )
            if object_score is None or activity_score is None:
                continue
            if object_score < ACTIVITY_OBJECT_MIN_SCORE:
                continue
            if activity_score < ACTIVITY_ACTION_MIN_SCORE:
                continue

            combined = 0.60 * object_score + 0.40 * activity_score
            if best_score is None or combined > best_score:
                best_score = combined
                best_pair = item

        if best_pair is None or best_score is None:
            return (
                "NO_MATCH",
                0.0,
                "The retrieved evidence does not sufficiently support the requested action/object relationship.",
                None,
                None,
            )

        best_evidence = best_pair["evidence"]
        return (
            "MATCH",
            _score_to_confidence(best_score),
            (
                "The evidence contains a candidate-performed activity "
                f"'{best_pair['action']}' applied to '{best_pair['object']}', "
                f"which is semantically compatible with the requested object "
                f"'{object_query}'."
            ),
            _build_evidence_payload(
                best_evidence,
                [
                    str(best_pair["action"]),
                    str(best_pair["object"]),
                    object_query,
                ],
            ),
            round(best_score, 6),
        )

    # Target-bearing activities are evaluated entirely inside the same atomic
    # evidence unit. We deliberately do NOT use neighboring units here.
    action_pairs: list[tuple[str, str]] = []
    object_pairs: list[tuple[str, str]] = []
    target_pairs: list[tuple[str, str]] = []
    full_requirement_pairs: list[tuple[str, str]] = []

    for item in action_object_candidates:
        evidence_text = str(item["evidence"].get("text", "")).strip()
        action_pairs.append((positive_query, evidence_text))
        object_pairs.append((object_query, str(item["object"]).strip()))
        target_pairs.append((target_query, evidence_text))
        full_requirement_pairs.append((generic_query, evidence_text))

    action_scores = _reranker.predict(action_pairs) if action_pairs else []
    object_scores = _reranker.predict(object_pairs) if object_pairs else []
    target_scores = _reranker.predict(target_pairs) if target_pairs else []
    full_requirement_scores = (
        _reranker.predict(full_requirement_pairs)
        if full_requirement_pairs
        else []
    )

    best_pair = None
    best_score = None
    best_full_score = None

    for index, item in enumerate(action_object_candidates):
        action_score = (
            float(action_scores[index])
            if index < len(action_scores)
            else None
        )
        object_score = (
            float(object_scores[index])
            if index < len(object_scores)
            else None
        )
        target_score = (
            float(target_scores[index])
            if index < len(target_scores)
            else None
        )
        full_score = (
            float(full_requirement_scores[index])
            if index < len(full_requirement_scores)
            else None
        )

        if (
            action_score is None
            or object_score is None
            or target_score is None
            or full_score is None
        ):
            continue
        # The requested action has already been structurally verified by
        # _extract_action_object_phrases(), which only returns candidate-
        # performed actions from the requested action family.  Therefore the
        # CrossEncoder action score is a ranking signal here, not a hard
        # rejection gate.  A hard action-score gate can reject valid semantic
        # realizations such as "built a RAG-based AI system" for a broader
        # requirement like "built products with AI" even though the same
        # evidence unit proves the requested action/object/target relationship.
        if full_score < ACTIVITY_JOINT_MIN_SCORE:
            continue

        evidence_text = str(item["evidence"].get("text", "")).strip()
        lexical_target = _target_is_lexically_supported(
            target_query,
            evidence_text,
        )
        target_attached = _target_is_attached_to_action_object(
            target_query,
            evidence_text,
            str(item["action"]),
            str(item["object"]),
        )

        # A target must be explicitly represented or semantically supported,
        # and it must be attached to the candidate's action/object rather than
        # merely appearing elsewhere in the same sentence.
        if not target_attached:
            continue
        if not lexical_target and target_score < SEMANTIC_VALIDATION_MIN_SCORE:
            continue

        # The complete requirement must be at least as informative as the
        # action-only evidence. A small configurable margin prevents a generic
        # action match from winning when the target relationship is weak.
        if full_score + ACTIVITY_ACTION_MARGIN < action_score:
            continue

        target_in_object = _contains_target_tokens(
            target_query,
            str(item["object"]),
        )

        # When the target is literally part of the extracted action object
        # (for example, "developed AI-powered web applications"), the object
        # itself already expresses the requested target relationship. In that
        # construction, requiring a separate CrossEncoder score for
        # "products" vs. "AI-powered web applications" is unnecessarily
        # restrictive and can reject valid semantic equivalents.
        #
        # When the target is attached through a relation clause instead
        # (for example, "built products using AI"), keep the object-level
        # semantic gate because the requested object must independently match.
        if not target_in_object and object_score < ACTIVITY_OBJECT_MIN_SCORE:
            continue

        # Object relevance remains part of ranking in every case. It is not
        # allowed to override the structural relationship checks above.
        combined = (
            0.40 * full_score
            + 0.20 * action_score
            + 0.25 * object_score
            + 0.15 * target_score
        )

        if best_score is None or combined > best_score:
            best_score = combined
            best_full_score = full_score
            best_pair = item

    if best_pair is None or best_score is None:
        return (
            "NO_MATCH",
            0.0,
            (
                "The retrieved evidence contains activity-related material, "
                f"but no single evidence unit sufficiently supports the complete "
                f"relationship between the candidate's activity, '{object_query}', "
                f"and target '{target_query}'."
            ),
            None,
            None,
        )

    best_evidence = best_pair["evidence"]
    return (
        "MATCH",
        _score_to_confidence(best_score),
        (
            "The same evidence unit contains a candidate-performed activity "
            f"'{best_pair['action']}' applied to '{best_pair['object']}', "
            f"and supports the requested target '{target_query}'."
        ),
        _build_evidence_payload(
            best_evidence,
            [
                str(best_pair["action"]),
                str(best_pair["object"]),
                object_query,
                target_query,
            ],
        ),
        round(best_full_score if best_full_score is not None else best_score, 6),
    )


def _validate_requirement(



    requirement: dict,



    index: int,



    evidence: list[dict],



) -> RequirementValidation:



    requirement_id = _requirement_id(requirement, index)



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



        if not text or not _matches_requirement_scope(requirement, item):



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



        usable_evidence = [



            item



            for item in usable_evidence



            if _is_recent_evidence(item, int(recency_months))



        ]



        if not usable_evidence:



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



    requirement_type = str(requirement.get("type") or "").upper()



    if requirement_type == "EXPERIENCE" and str(requirement.get("scope") or "").upper() == "DOMAIN":



        status, confidence, reason, matched_evidence = _domain_experience_validation(requirement, usable_evidence)



        return RequirementValidation(



            requirement_id=requirement_id,



            status=status,



            confidence=confidence,



            reason=reason,



            evidence_score=confidence,



            matched_evidence=matched_evidence,



        )



    if requirement_type == "ACTIVITY":

        (
            status,
            confidence,
            reason,
            matched_evidence,
            evidence_score,
        ) = _activity_validation(requirement, usable_evidence)
        return RequirementValidation(
            requirement_id=requirement_id,
            status=status,
            confidence=confidence,
            reason=reason,
            evidence_score=evidence_score,
            matched_evidence=matched_evidence,
        )

    best_score, best_index = _best_cross_encoder_score(query, usable_evidence)



    if best_score is None or best_index is None:



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



                "to the requested requirement above the validation threshold."



            ),



            evidence_score=round(best_score, 6),



            matched_evidence=_build_evidence_payload(



                usable_evidence[best_index],



                _highlight_query_phrases(query),



            ),



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



        matched_evidence=None,



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

      3. for target-bearing activities, action + object + target support
         from the SAME atomic evidence unit,

      4. no cross-sentence or cross-bullet composition of unrelated evidence,

      5. semantic support for paraphrases without allowing a target-only
         mention to satisfy the activity relationship.

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



        if not (



            requirement.get("type") in {"ACTIVITY", "INDUSTRY", "OTHER"}



            or (requirement.get("type") == "EXPERIENCE" and requirement.get("scope") == "DOMAIN")



        ):



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
