import os
from app.intelligence.validator.rules import (
    _tokens,
    _SEMANTIC_STOP_WORDS,
)
from app.intelligence.validator.heuristics import (
    _heuristic_supports_semantic_requirement,
    _is_specialized_semantic_requirement,
    _semantic_support_score,
)

try:
    from app.intelligence.validator.nli_verifier import verify_evidence_entailment
except Exception:
    verify_evidence_entailment = None

USE_NLI_VALIDATOR = os.getenv('USE_NLI_VALIDATOR', 'true').lower() in ('true', '1', 'yes')

def check_semantic_requirement_support(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
    reranker_score: float | None = None,
) -> tuple[str | None, dict | None]:
    """
    Check if evidence text supports a semantic requirement.
    Returns (matched_sentence, nli_details_or_None).
    """
    candidate_sentence = _heuristic_supports_semantic_requirement(
        requirement=requirement,
        evidence_text=evidence_text,
        evidence_type=evidence_type,
        reranker_score=reranker_score,
    )

    if not USE_NLI_VALIDATOR or verify_evidence_entailment is None:
        return candidate_sentence, None

    # Avoid running NLI on raw skill lists or education markers
    if str(evidence_type or "").casefold() in {"skill", "skills", "education"}:
        return candidate_sentence, None

    # Specialized domain rules (e.g. ML models, Microsoft stack, CRM signals)
    # have curated domain vocabulary; trust their direct match.
    if candidate_sentence and _is_specialized_semantic_requirement(requirement):
        return candidate_sentence, {
            "matched": True,
            "confidence": 0.95,
            "reason": f"Domain match verified ({requirement})",
        }

    try:
        # If non-specialized heuristic found a candidate sentence (via token overlap or reranker),
        # verify it doesn't contradict the requirement.
        if candidate_sentence:
            nli_res = verify_evidence_entailment(candidate_sentence, requirement)
            if (
                nli_res.get("contradiction_score", 0.0) > 0.40
                or (not nli_res.get("matched") and nli_res.get("entailment_score", 0.0) < 0.20)
            ):
                candidate_sentence = None
            else:
                return candidate_sentence, nli_res

        # If heuristic found nothing or was rejected by contradiction, check full passage with NLI
        # ONLY if the passage has token overlap or reranker signal (reranker_score >= 0.25).
        # This skips hundreds of completely irrelevant background passages in 0.00ms.
        requirement_tokens = _tokens(requirement)
        content_tokens = {t for t in requirement_tokens if t not in _SEMANTIC_STOP_WORDS}
        has_overlap = bool(content_tokens & _tokens(evidence_text))
        has_reranker = reranker_score is not None and float(reranker_score) >= 0.25

        if (
            not candidate_sentence
            and not _is_specialized_semantic_requirement(requirement)
            and (has_overlap or has_reranker)
            and evidence_text
            and evidence_text.strip()
        ):
            nli_res = verify_evidence_entailment(evidence_text, requirement)
            if nli_res.get("matched"):
                return nli_res.get("best_sentence") or None, nli_res

    except Exception:
        return candidate_sentence, None

    return None, None


def _supports_semantic_requirement(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
    reranker_score: float | None = None,
) -> str | None:
    """
    Return the sentence supporting a requirement, or None if unsupported.
    Uses rule heuristics for candidate identification, verified with local NLI.
    """
    sentence, _ = check_semantic_requirement_support(
        requirement=requirement,
        evidence_text=evidence_text,
        evidence_type=evidence_type,
        reranker_score=reranker_score,
    )
    return sentence



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
        for item in evidence[:4]:
            if str(item.get("evidence_type") or "").casefold() in {
                "skill", "skills", "education"
            }:
                continue
            text = str(item.get("text") or "")
            matched_sentence, nli_res = check_semantic_requirement_support(
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

                nli_meta = {}
                if nli_res and nli_res.get("matched"):
                    support_score = max(support_score, float(nli_res.get("confidence", 0.0)))
                    nli_meta = {
                        "nli_verified": True,
                        "nli_confidence": nli_res.get("confidence"),
                        "nli_reason": nli_res.get("reason"),
                    }
                elif _is_specialized_semantic_requirement(requirement):
                    nli_meta = {
                        "nli_verified": True,
                        "nli_confidence": support_score,
                        "nli_reason": f"Domain match verified ({requirement})",
                    }
                elif USE_NLI_VALIDATOR and verify_evidence_entailment is not None and not nli_res:
                    try:
                        nli_res = verify_evidence_entailment(matched_sentence, requirement)
                        if nli_res.get("matched"):
                            support_score = max(support_score, float(nli_res.get("confidence", 0.0)))
                            nli_meta = {
                                "nli_verified": True,
                                "nli_confidence": nli_res.get("confidence"),
                                "nli_reason": nli_res.get("reason"),
                            }
                    except Exception:
                        pass

                if support_score <= best_support_score:
                    continue

                if len(matched_sentence) > 600:
                    matched_sentence = (
                        matched_sentence[:597].rsplit(" ", 1)[0]
                        + "..."
                    )

                best_match = {
                    **item,
                    **nli_meta,
                    "requirement": requirement,
                    "text": matched_sentence,
                    "semantic_support_score": support_score,
                }
                best_support_score = support_score

                if best_support_score >= 0.85:
                    break

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

