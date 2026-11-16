from functools import lru_cache
import logging
import os
import re
from threading import Lock

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

NLI_MODEL_NAME = os.getenv(
    "NLI_MODEL_NAME",
    "cross-encoder/nli-deberta-v3-small",
)

# Minimum entailment probability required to qualify candidate evidence
NLI_ENTAILMENT_THRESHOLD = float(
    os.getenv("NLI_ENTAILMENT_THRESHOLD", "0.50")
)

_nli_model: CrossEncoder | None = None
_nli_lock = Lock()
_label_map: dict[int, str] | None = None


def _get_nli_model() -> CrossEncoder:
    """Lazy load the NLI CrossEncoder model into CPU memory."""
    global _nli_model, _label_map

    if _nli_model is None:
        with _nli_lock:
            if _nli_model is None:
                logger.info("Loading local NLI CrossEncoder model: %s", NLI_MODEL_NAME)
                try:
                    # Prefer local cached files to avoid network latency/timeouts
                    model = CrossEncoder(NLI_MODEL_NAME, max_length=256, local_files_only=True)
                except Exception:
                    model = CrossEncoder(NLI_MODEL_NAME, max_length=256)

                # Dynamically extract label mapping from model config
                raw_labels = getattr(
                    model.model.config,
                    "id2label",
                    {0: "contradiction", 1: "entailment", 2: "neutral"},
                )
                _label_map = {idx: str(label).lower() for idx, label in raw_labels.items()}
                _nli_model = model

    return _nli_model


def format_hypothesis(requirement: str) -> str:
    """
    Format a recruiter requirement into a clean natural language hypothesis.
    
    Examples:
      'built products with AI' -> 'The candidate has built products with AI.'
      'worked in B2B sales' -> 'The candidate has worked in B2B sales.'
      'experience with CRM platforms' -> 'The candidate has experience with CRM platforms.'
      'experience designing distributed systems' -> 'The candidate has experience designing distributed systems.'
    """
    cleaned = requirement.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"^[,\s;.-]+|[,\s;.-]+$", "", cleaned)
    cleaned = re.sub(
        r"^\b(?:\d+\+?\s*(?:years?|yrs?|months?)\s+(?:of\s+)?(?:experience\s+(?:in|with|of)?|tenure)?)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    lower = cleaned.lower()

    if lower.startswith(("the candidate", "this person", "candidate")):
        hypothesis = cleaned
    elif lower.startswith(("has ", "have ", "had ")):
        hypothesis = f"The candidate has {cleaned.split(maxsplit=1)[1]}."
    elif lower.startswith((
        "built ", "worked ", "developed ", "led ", "managed ",
        "created ", "designed ", "implemented ", "spearheaded ",
    )):
        hypothesis = f"The candidate has {cleaned}."
    elif lower.startswith((
        "experience in ", "experience with ", "experience of ", "experience ",
        "hands-on experience ", "prior experience ", "proven experience ",
    )):
        hypothesis = f"The candidate has {cleaned}."
    elif lower.startswith((
        "background in ", "knowledge of ", "skills in ", "proficiency in ",
    )):
        hypothesis = f"The candidate has {cleaned}."
    elif re.match(r"^[a-z]+ing\b", lower):
        hypothesis = f"The candidate has experience {cleaned}."
    else:
        hypothesis = f"The candidate has experience with {cleaned}."

    if not hypothesis.endswith("."):
        hypothesis += "."

    return hypothesis


def split_sentences(text: str) -> list[str]:
    """Split resume evidence into candidate sentences and bullet points."""
    if not text:
        return []

    # Split by common resume delimiters (bullet points, newlines, semicolons, periods)
    raw_segments = re.split(r"[\n\r•·\t]+|[;.]\s+", text)
    sentences = []

    for segment in raw_segments:
        clean = " ".join(segment.strip().split())
        if len(clean) >= 15:  # Ignore fragments with fewer than 15 characters
            sentences.append(clean)

    return sentences or [text.strip()]


def _cached_verify_evidence_entailment(
    evidence_text: str,
    requirement: str,
    threshold: float,
) -> tuple:
    """Cached worker for NLI entailment scoring."""
    hypothesis = format_hypothesis(requirement)
    sentences = split_sentences(evidence_text)

    if not sentences:
        sentences = [evidence_text.strip()]

    model = _get_nli_model()
    pairs = [(sentence, hypothesis) for sentence in sentences]

    # Batch prediction with softmax for normalized probabilities (progress bar silenced)
    raw_scores = model.predict(pairs, batch_size=32, apply_softmax=True, show_progress_bar=False)

    # In case of single sentence prediction returning 1D array
    if len(pairs) == 1 and hasattr(raw_scores, "ndim") and raw_scores.ndim == 1:
        raw_scores = [raw_scores]

    best_entailment = 0.0
    best_sentence = ""
    best_contradiction = 0.0
    best_neutral = 0.0

    global _label_map
    label_map = _label_map or {0: "contradiction", 1: "entailment", 2: "neutral"}

    for idx, sentence_scores in enumerate(raw_scores):
        score_dict = {}
        for class_idx, class_score in enumerate(sentence_scores):
            label_name = label_map.get(class_idx, "unknown")
            score_dict[label_name] = float(class_score)

        entailment = score_dict.get("entailment", 0.0)
        contradiction = score_dict.get("contradiction", 0.0)
        neutral = score_dict.get("neutral", 0.0)

        if entailment > best_entailment:
            best_entailment = entailment
            best_contradiction = contradiction
            best_neutral = neutral
            best_sentence = sentences[idx]

    is_matched = (
        best_entailment >= threshold
        and best_contradiction <= 0.40
    )

    if is_matched:
        reason = f"Verified via evidence passage (entailment: {best_entailment:.0%})"
    elif best_contradiction > 0.50:
        reason = "Passage contradicts requirement or describes unrelated non-primary work."
    else:
        reason = f"Passage does not sufficiently prove requirement (confidence: {best_entailment:.0%})."

    return (
        is_matched,
        round(best_entailment, 4),
        round(best_entailment, 4),
        round(best_contradiction, 4),
        round(best_neutral, 4),
        best_sentence,
        hypothesis,
        reason,
    )


def verify_evidence_entailment(
    evidence_text: str,
    requirement: str,
    threshold: float = NLI_ENTAILMENT_THRESHOLD,
) -> dict:
    """
    Verify whether an evidence passage logically entails a recruiter requirement.
    
    Returns a dict with:
      - matched: bool (True if entailment probability >= threshold)
      - confidence: float (0.0 to 1.0)
      - entailment_score: float
      - contradiction_score: float
      - neutral_score: float
      - best_sentence: str
      - reason: str (Human-readable explanation for UI badges)
    """
    if not evidence_text or not evidence_text.strip():
        return {
            "matched": False,
            "confidence": 0.0,
            "entailment_score": 0.0,
            "contradiction_score": 0.0,
            "neutral_score": 0.0,
            "best_sentence": "",
            "reason": "No evidence text provided.",
        }

    res_tuple = _cached_verify_evidence_entailment(
        evidence_text.strip(),
        requirement.strip(),
        threshold,
    )

    return {
        "matched": res_tuple[0],
        "confidence": res_tuple[1],
        "entailment_score": res_tuple[2],
        "contradiction_score": res_tuple[3],
        "neutral_score": res_tuple[4],
        "best_sentence": res_tuple[5],
        "hypothesis": res_tuple[6],
        "reason": res_tuple[7],
    }
