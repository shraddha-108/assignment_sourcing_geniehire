import re
import math
from app.search.normalization import (
    industry_evidence_matches,
    industry_evidence_terms,
)
from app.intelligence.validator.rules import (
    _tokens,
    _semantic_sentences,
    _SEMANTIC_STOP_WORDS,
    _BUILD_ACTIONS,
    _INTEGRATION_ACTIONS,
    _AI_TERMS,
    _ML_FRAMEWORK_TERMS,
    _ML_METHOD_TERMS,
    _PROJECT_CONTEXT_TERMS,
    _ML_IMPLEMENTATION_TERMS,
    _ML_WORK_ACTIONS,
    _PRODUCT_TERMS,
    _BUILT_PRODUCT_TERMS,
    SEMANTIC_SUPPORT_MIN_RERANKER_SCORE,
    _CUSTOMER_RELATIONSHIP_SIGNALS,
    _CUSTOMER_RELATIONSHIP_ADJACENT_SIGNALS,
    _CUSTOMER_RELATIONSHIP_WORK_ACTIONS,
    _CUSTOMER_RELATIONSHIP_ROLE_TITLES,
    _DISTRIBUTED_SYSTEM_SIGNALS,
    _SCALABILITY_SIGNALS,
)


def is_customer_relationship_requirement(requirement: str) -> bool:
    return bool(_CUSTOMER_RELATIONSHIP_SIGNALS.search(requirement))


def customer_relationship_partial_evidence(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
) -> str | None:
    if not is_customer_relationship_requirement(requirement):
        return None
    if (evidence_type or "").casefold() in {"skill", "skills", "education"}:
        return None
    for sentence in _semantic_sentences(evidence_text):
        has_direct_signal = bool(_CUSTOMER_RELATIONSHIP_SIGNALS.search(sentence))
        has_adjacent_signal = bool(
            _CUSTOMER_RELATIONSHIP_ADJACENT_SIGNALS.search(sentence)
        )
        has_work_context = bool(
            _CUSTOMER_RELATIONSHIP_WORK_ACTIONS.search(sentence)
            or _CUSTOMER_RELATIONSHIP_ROLE_TITLES.search(sentence)
        )
        if (
            has_adjacent_signal and not has_direct_signal
        ) or (
            has_direct_signal and not has_work_context
        ):
            return sentence
    return None


def customer_relationship_partial_reason(evidence_text: str) -> str:
    if (
        _CUSTOMER_RELATIONSHIP_ADJACENT_SIGNALS.search(evidence_text)
        and not _CUSTOMER_RELATIONSHIP_SIGNALS.search(evidence_text)
    ):
        return "Related Dynamics experience was found, but CRM-specific work was not confirmed."
    return "A CRM platform or project is mentioned, but hands-on CRM work is unclear."


def _has_ai_concept(tokens: set[str]) -> bool:
    return bool(tokens & _AI_TERMS) or {
        "artificial", "intelligence"
    }.issubset(tokens) or {"machine", "learning"}.issubset(tokens)


def _is_ai_build_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_to_build = bool(tokens & _BUILD_ACTIONS)
    asks_about_ai = _has_ai_concept(tokens)
    return asks_to_build and asks_about_ai


def _is_ecommerce_build_requirement(requirement: str) -> bool:
    text = requirement.casefold().replace("e-commerce", "ecommerce")
    tokens = _tokens(text)
    asks_to_build = bool(tokens & _BUILD_ACTIONS)
    asks_about_ecommerce = bool(
        "ecommerce" in tokens
        or {"online", "store"}.issubset(tokens)
        or {"shopping", "cart"}.issubset(tokens)
    )
    return asks_to_build and asks_about_ecommerce


def _supports_ecommerce_build(sentence: str) -> bool:
    text = sentence.casefold().replace("e-commerce", "ecommerce")
    tokens = _tokens(text)
    ecommerce_context = bool(
        "ecommerce" in tokens
        or {"online", "store"}.issubset(tokens)
        or {"shopping", "cart"}.issubset(tokens)
        or {"online", "sales"}.issubset(tokens)
        or {"online", "ordering"}.issubset(tokens)
        or {"retail", "platform"}.issubset(tokens)
    )
    return ecommerce_context and bool(tokens & _BUILD_ACTIONS)


def _is_distributed_system_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_about_system_design = bool(
        tokens & {"system", "systems", "architecture", "platform", "platforms"}
    )
    asks_about_distributed_scale = bool(
        tokens & {"distributed", "scalable", "scalability"}
    )
    return asks_about_system_design and asks_about_distributed_scale


def _supports_distributed_system_design(sentence: str) -> bool:
    tokens = _tokens(sentence)
    has_design_action = bool(tokens & _BUILD_ACTIONS)
    has_distributed_evidence = bool(_DISTRIBUTED_SYSTEM_SIGNALS.search(sentence))
    has_scalability_evidence = bool(_SCALABILITY_SIGNALS.search(sentence))
    return (
        has_design_action
        and has_distributed_evidence
        and has_scalability_evidence
    )


def _is_ml_project_requirement(requirement: str) -> bool:
    tokens = _tokens(requirement)
    asks_about_ml = (
        {"machine", "learning"}.issubset(tokens)
        or "ml" in tokens
        or {"deep", "learning"}.issubset(tokens)
    )
    asks_about_projects = bool(tokens & {"project", "projects"})
    return asks_about_ml and asks_about_projects


def _supports_ml_project(
    sentence: str,
    evidence_type: str | None,
) -> bool:
    tokens = _tokens(sentence)
    has_ml_signal = (
        {"machine", "learning"}.issubset(tokens)
        or "ml" in tokens
        or {"deep", "learning"}.issubset(tokens)
        or bool(tokens & _ML_FRAMEWORK_TERMS)
        or bool(tokens & _ML_METHOD_TERMS)
        or {"computer", "vision"}.issubset(tokens)
    )
    if not has_ml_signal:
        return False

    is_computer_vision = {"computer", "vision"}.issubset(tokens)
    has_implementation_detail = (
        bool(tokens & _ML_IMPLEMENTATION_TERMS)
        or is_computer_vision
    )
    explicit_ml_based_project = (
        "ml" in tokens
        and "based" in tokens
        and bool(tokens & _PROJECT_CONTEXT_TERMS)
        and (evidence_type or "").lower() == "project"
    )
    if not has_implementation_detail and not explicit_ml_based_project:
        return False

    has_work_action = bool(tokens & _ML_WORK_ACTIONS)
    if not has_work_action and not explicit_ml_based_project:
        return False

    if (evidence_type or "").lower() == "project":
        return True

    has_project_context = bool(tokens & _PROJECT_CONTEXT_TERMS)
    return has_project_context and has_work_action


def _supports_ai_build(sentence: str) -> bool:
    if re.search(r"\b(?:talent acquisition|recruitment|recruiting|sourc(?:ing|ed)|hiring|headcount)\b", sentence, re.IGNORECASE):
        if not re.search(r"\b(?:software|developer|engineer|model|algorithm|rag|inference)\b", sentence, re.IGNORECASE):
            return False

    if re.search(
        r"\b(?:outreach|prospecting|lead\s+gen\w*|sales\s+emails?|cold\s+emails?|copywriting|"
        r"test\s+case\s+generation|test\s+data\s+prep\w*|autocomplete)\b",
        sentence,
        re.IGNORECASE,
    ):
        return False

    # Strip company name AI patterns like "Akni Ai Private limited" so company names don't trigger AI terms
    clean_sentence = re.sub(
        r"\b[A-Za-z0-9]+\s+Ai\s+(?:Private|Pvt\.?|Limited|Ltd\.?|LLP|Inc\.?|Technologies|Solutions)\b",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    words = re.findall(r"[a-z0-9+#.]+", clean_sentence.lower())
    action_positions = [
        index
        for index, word in enumerate(words)
        if word in _BUILD_ACTIONS
    ]
    integration_positions = [
        index
        for index, word in enumerate(words)
        if word in _INTEGRATION_ACTIONS
    ]
    product_positions = [
        index
        for index, word in enumerate(words)
        if word in _PRODUCT_TERMS
    ]
    ai_positions = [
        index
        for index, word in enumerate(words)
        if word in _AI_TERMS
    ]
    built_product_positions = [
        index
        for index, word in enumerate(words)
        if word in _BUILT_PRODUCT_TERMS
    ]

    direct_build_pairs = [
        (action, product, ai)
        for action in action_positions
        for product in product_positions
        for ai in ai_positions
        if abs(action - product) <= 8
        and abs(ai - product) <= 6
        and abs(action - ai) <= 8
    ]

    integration_pairs = [
        (action, product, ai)
        for action in integration_positions
        for product in built_product_positions
        for ai in ai_positions
        if abs(action - product) <= 6
        and abs(ai - product) <= 4
        and abs(action - ai) <= 6
    ]

    pairs = direct_build_pairs or integration_pairs
    return bool(pairs)


def _semantic_support_score(
    requirement: str,
    sentence: str,
    evidence_type: str | None,
) -> float:
    if _CUSTOMER_RELATIONSHIP_SIGNALS.search(requirement):
        base_score = 0.9 if _CUSTOMER_RELATIONSHIP_SIGNALS.search(sentence) else 0.0
    elif industry_evidence_terms(requirement):
        base_score = 0.85 if industry_evidence_matches(sentence, requirement) else 0.0
    elif _is_distributed_system_requirement(requirement):
        base_score = 0.9
    elif _is_ecommerce_build_requirement(requirement):
        base_score = 0.85
    elif re.search(r"\bback[- ]end\s+(?:tech|technolog(?:y|ies|ical))\b", requirement, re.IGNORECASE):
        base_score = 0.85
    elif _is_ml_project_requirement(requirement):
        tokens = _tokens(sentence)
        base_score = (
            1.0
            if {"machine", "learning"}.issubset(tokens)
            else 0.9
        )
    elif _is_ai_family_requirement(requirement):
        base_score = 0.95
    elif _is_ai_build_requirement(requirement):
        clean_sentence = re.sub(
            r"\b[A-Za-z0-9]+\s+Ai\s+(?:Private|Pvt\.?|Limited|Ltd\.?|LLP|Inc\.?|Technologies|Solutions)\b",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        words = re.findall(r"[a-z0-9+#.]+", clean_sentence.lower())
        action_positions = [
            index for index, word in enumerate(words)
            if word in _BUILD_ACTIONS
        ]
        product_positions = [
            index for index, word in enumerate(words)
            if word in _PRODUCT_TERMS
        ]
        ai_positions = [
            index for index, word in enumerate(words)
            if word in _AI_TERMS
        ]
        distances = [
            abs(action - product)
            + abs(ai - product)
            + abs(action - ai)
            for action in action_positions
            for product in product_positions
            for ai in ai_positions
            if abs(action - product) <= 8
            and abs(ai - product) <= 6
            and abs(action - ai) <= 8
        ]

        if not distances:
            integration_positions = [
                index for index, word in enumerate(words)
                if word in _INTEGRATION_ACTIONS
            ]
            built_product_positions = [
                index for index, word in enumerate(words)
                if word in _BUILT_PRODUCT_TERMS
            ]
            distances = [
                abs(action - product)
                + abs(ai - product)
                + abs(action - ai)
                for action in integration_positions
                for product in built_product_positions
                for ai in ai_positions
                if abs(action - product) <= 6
                and abs(ai - product) <= 4
                and abs(action - ai) <= 6
            ]

        base_score = (
            0.7 + 0.3 * (1.0 - min(min(distances), 24) / 24.0)
            if distances
            else 0.0
        )
    else:
        content_tokens = {
            token
            for token in _tokens(requirement)
            if token not in _SEMANTIC_STOP_WORDS
        }
        sentence_tokens = _tokens(sentence)
        base_score = (
            len(content_tokens & sentence_tokens) / len(content_tokens)
            if content_tokens
            else 0.0
        )

    source_weight = {
        "project": 1.0,
        "experience": 0.98,
        "summary": 0.85,
        "skill": 0.80,
    }.get((evidence_type or "").lower(), 0.90)
    return base_score * source_weight


def _is_specialized_semantic_requirement(requirement: str) -> bool:
    return bool(
        _CUSTOMER_RELATIONSHIP_SIGNALS.search(requirement)
        or _is_ml_project_requirement(requirement)
        or _is_ecommerce_build_requirement(requirement)
        or _is_distributed_system_requirement(requirement)
        or _is_microsoft_ecosystem_requirement(requirement)
        or _is_cloud_technology_requirement(requirement)
        or _is_cicd_requirement(requirement)
        or _is_ai_family_requirement(requirement)
        or industry_evidence_terms(requirement)
    )


def _heuristic_supports_semantic_requirement(
    requirement: str,
    evidence_text: str,
    evidence_type: str | None = None,
    reranker_score: float | None = None,
) -> str | None:
    requirement_tokens = _tokens(requirement)
    content_tokens = {
        token
        for token in requirement_tokens
        if token not in _SEMANTIC_STOP_WORDS
    }
    specialized_requirement = _is_specialized_semantic_requirement(requirement)

    if industry_evidence_terms(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if industry_evidence_matches(sentence, requirement):
                return sentence

    if _CUSTOMER_RELATIONSHIP_SIGNALS.search(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if (
                _CUSTOMER_RELATIONSHIP_SIGNALS.search(sentence)
                and (
                    _CUSTOMER_RELATIONSHIP_WORK_ACTIONS.search(sentence)
                    or _CUSTOMER_RELATIONSHIP_ROLE_TITLES.search(sentence)
                )
            ):
                return sentence

    if _is_microsoft_ecosystem_requirement(requirement):
        microsoft_signals = re.compile(
            r"(?<!\w)\.net\b|\bc\s*#\b|\b(?:d365|dynamics\s*365|dynamics\s+(?:crm|customer engagement)|"
            r"business central|power\s*(?:apps|automate|bi|platform|pages)|azure|"
            r"microsoft\s*(?:365|365|office\s*365)|sharepoint|teams|sql\s*server|"
            r"entra\s*id|azure\s*active\s*directory)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if microsoft_signals.search(sentence):
                return sentence

    if _is_cloud_technology_requirement(requirement):
        cloud_signals = re.compile(
            r"\b(?:aws|amazon\s+web\s+services|azure|microsoft\s+azure|"
            r"gcp|google\s+cloud(?:\s+platform)?|oracle\s+cloud|ibm\s+cloud|"
            r"cloud\s+(?:computing|infrastructure|platform|services?)|"
            r"kubernetes|serverless|iaas|paas|cloud\s+storage)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if cloud_signals.search(sentence):
                return sentence

    if _is_cicd_requirement(requirement):
        cicd_signals = re.compile(
            r"\b(?:ci[/-]?cd|continuous\s+integration|continuous\s+deployment|continuous\s+delivery|"
            r"jenkins|github\s+actions|gitlab\s*ci|gitlab\s+pipelines?|circleci|travis(?:\s*ci)?|"
            r"argocd|argo\s*cd|bitbucket\s+pipelines?|bamboo|teamcity|buildkite|spinnaker|flux\s*cd|"
            r"deployment\s+pipelines?|build\s+pipelines?|release\s+pipelines?|ci\s+pipelines?|cd\s+pipelines?)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if cicd_signals.search(sentence):
                return sentence
        return None

    if re.search(r"\bback[- ]end\s+(?:tech|technolog(?:y|ies|ical))\b", requirement, re.IGNORECASE):
        backend_signals = re.compile(
            r"\b(backend|back-end|server[- ]side|rest(?:ful)?|graphql|api|apis|"
            r"database|sql|postgres(?:ql)?|mysql|mongodb|redis|microservices?|"
            r"fastapi|django|flask|spring|express(?:\.js)?|node\.js|asp\.net)\b",
            re.IGNORECASE,
        )
        for sentence in _semantic_sentences(evidence_text):
            if backend_signals.search(sentence):
                return sentence

    if _is_ecommerce_build_requirement(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if _supports_ecommerce_build(sentence):
                return sentence

    if _is_distributed_system_requirement(requirement):
        for sentence in _semantic_sentences(evidence_text):
            if _supports_distributed_system_design(sentence):
                return sentence

    if _is_ai_family_requirement(requirement) and not _is_ai_build_requirement(requirement) and not _is_ml_project_requirement(requirement):
        is_hiring_query = bool(re.search(r"\b(?:hir\w*|recruit\w*|talent|sourc\w*)\b", requirement, re.IGNORECASE))
        if is_hiring_query:
            ai_hiring_signals = re.compile(
                r"\b(?:ai|chatgpt|claude|copilot|generative\s+ai|llm)\b.{0,60}\b(?:hir\w*|recruit\w*|talent|sourc\w*|screen\w*|interview\w*|candidate|profiles?)\b|"
                r"\b(?:hir\w*|recruit\w*|talent|sourc\w*|screen\w*|interview\w*|candidate|profiles?)\b.{0,60}\b(?:ai|chatgpt|claude|copilot|generative\s+ai|llm)\b",
                re.IGNORECASE,
            )
            for sentence in _semantic_sentences(evidence_text):
                if ai_hiring_signals.search(sentence):
                    return sentence
            return None
        else:
            consumer_task = re.compile(
                r"\b(?:outreach|prospecting|lead\s+gen\w*|sales\s+emails?|cold\s+emails?|copywriting|"
                r"test\s+case\s+generation|test\s+data\s+prep\w*|autocomplete)\b",
                re.IGNORECASE,
            )
            tech_ai_signals = re.compile(
                r"\b(?:pytorch|tensorflow|keras|scikit[- ]learn|sklearn|xgboost|lightgbm|huggingface|"
                r"transformers|rag|retrieval\s+augmented|langchain|llamaindex|vector\s+(?:db|database|databases)|"
                r"qdrant|pinecone|chromadb|weaviate|faiss|fine[- ]tuning|fine[- ]tuned|embeddings?|"
                r"neural\s+networks?|deep\s+learning|computer\s+vision|nlp|"
                r"(?:openai|gemini|claude|anthropic|llm|llms)\s+apis?|"
                r"(?:built|develop\w*|integrat\w*|implement\w*|deploy\w*|train\w*|architect\w*)\s+.{0,40}\b(?:ai|llm|llms|chatbot|agent|model))\b",
                re.IGNORECASE,
            )
            for sentence in _semantic_sentences(evidence_text):
                if tech_ai_signals.search(sentence) and not consumer_task.search(sentence):
                    return sentence
            return None

    sentences = _semantic_sentences(evidence_text)
    for sentence in sentences:
        sentence_tokens = _tokens(sentence)

        if _is_ml_project_requirement(requirement):
            if _supports_ml_project(sentence, evidence_type):
                return sentence
            continue

        if _is_ai_build_requirement(requirement):
            if _supports_ai_build(sentence):
                return sentence
            continue

        if _is_ecommerce_build_requirement(requirement):
            if _supports_ecommerce_build(sentence):
                return sentence
            continue

        if _is_distributed_system_requirement(requirement):
            if _supports_distributed_system_design(sentence):
                return sentence
            continue

        if not content_tokens:
            continue

        overlap = len(content_tokens & sentence_tokens)
        required_overlap = max(1, math.ceil(len(content_tokens) * 0.6))

        if overlap >= required_overlap:
            return sentence

    if (
        not specialized_requirement
        and reranker_score is not None
        and float(reranker_score) >= SEMANTIC_SUPPORT_MIN_RERANKER_SCORE
        and sentences
    ):
        return max(
            sentences,
            key=lambda sentence: len(content_tokens & _tokens(sentence)),
        )

    return None


def _is_microsoft_ecosystem_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\b(?:microsoft\s+(?:technology|technologies|ecosystem|stack)|d365|dynamics\s*365|dynamics\s*ax)\b",
        requirement,
        re.IGNORECASE,
    ))


def _is_cloud_technology_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\bcloud\s+(?:technology|technologies|ecosystem|platforms?)\b",
        requirement,
        re.IGNORECASE,
    ))


def _is_ai_family_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\b(?:artificial\s+intelligence|\bAI\b|genai|generative\s+ai|machine\s+learning|\bML\b)\b",
        requirement,
        re.IGNORECASE,
    ))


def _is_cicd_requirement(requirement: str) -> bool:
    return bool(re.search(
        r"\b(?:ci[/-]?cd|continuous\s+integration|continuous\s+deployment|continuous\s+delivery)\b",
        requirement,
        re.IGNORECASE,
    ))
