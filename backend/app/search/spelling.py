"""Local spell suggestions for recruiter search queries (no LLM, no API cost)."""

import re
from importlib.resources import files
from typing import Callable, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session
from symspellpy import SymSpell, Verbosity

# Acronyms and short terms that must never be "corrected".
PROTECTED = {
    "ai", "ml", "llm", "llms", "sql", "aws", "gcp", "crm", "erp", "sap","qa", "devops",
    "api", "apis", "rag", "genai", "usa", "uk", "d365", "c++", "c#", "nodejs","springboot", "reactjs", "angularjs", "vuejs", "django", "flask", "fastapi",
}

# Common query words that may not appear in your data.
QUERY_WORDS = [
    "candidate", "candidates", "recruiter", "recruiters", "developer",
    "developers", "engineer", "engineers", "experience", "experienced",
    "looking", "senior", "junior", "fresher", "graduate", "remote", "hybrid","onboarding", "contract", "permanent", "fulltime", "parttime", "internship","springboot"
    "backend", "frontend", "fullstack", "analyst", "scientist", "manager","infosys", "tcs", "wipro", "hcl", "accenture", "capgemini", "cognizant",
]

DOMAIN_BOOST = 500_000_000   # beats similar general-English words
WORD_RE = re.compile(r"[A-Za-z]+")

_sym: SymSpell | None = None
_known: set[str] = set(PROTECTED)


# ---------- setup ----------

def build_speller(domain_terms: Iterable[str] = ()) -> None:
    """Build the global speller. Call once at startup (and after big data changes)."""
    global _sym, _known
    sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    pkg = files("symspellpy")
    sym.load_dictionary(
        str(pkg / "frequency_dictionary_en_82_765.txt"), term_index=0, count_index=1
    )

    known = set(PROTECTED)
    for term in [*QUERY_WORDS, *domain_terms]:
        for word in re.findall(r"[a-z0-9+#.]+", (term or "").lower()):
            sym.create_dictionary_entry(word, DOMAIN_BOOST)
            known.add(word)

    _sym, _known = sym, known


def load_domain_terms(db: Session) -> list[str]:
    """Pull skills, titles, companies, cities, names from your DB.
    ADJUST table/column names to your schema."""
    queries = [
        "SELECT DISTINCT name FROM skills",
        "SELECT DISTINCT job_title FROM candidates",
        "SELECT DISTINCT current_company FROM candidates",
        "SELECT DISTINCT location FROM candidates",
        "SELECT DISTINCT full_name FROM candidates",
    ]
    terms: list[str] = []
    for q in queries:
        try:
            terms += [r[0] for r in db.execute(text(q)) if r[0]]
        except Exception:
            db.rollback()   # a missing column shouldn't break startup
    return terms


# ---------- optional Postgres fallback ----------

def make_trigram_fallback(db: Session) -> Callable[[str], str | None]:
    """Fuzzy-match a word against skill names with pg_trgm.
    One-time SQL:
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE INDEX IF NOT EXISTS idx_skills_trgm
            ON skills USING gin (lower(name) gin_trgm_ops);
    """
    def fallback(word: str) -> str | None:
        row = db.execute(
            text(
                "SELECT lower(name) FROM skills "
                "WHERE similarity(lower(name), :w) >= 0.5 "
                "ORDER BY similarity(lower(name), :w) DESC LIMIT 1"
            ),
            {"w": word},
        ).first()
        return row[0] if row else None

    return fallback


# ---------- main function ----------

def _restore_case(original: str, corrected: str) -> str:
    if original.isupper():
        return corrected.upper()
    if original[:1].isupper():
        return corrected.capitalize()
    return corrected


def suggest_query_correction(
    query: str,
    fallback: Callable[[str], str | None] | None = None,
) -> str | None:
    """Return a corrected query, or None if nothing needs fixing."""
    if _sym is None:
        raise RuntimeError("Call build_speller() at startup first.")

    changed = False

    def fix(match: re.Match) -> str:
        nonlocal changed
        original = match.group(0)
        low = original.lower()
        s, e = match.start(), match.end()
        text_ = match.string

        # Leave alone: tiny words, acronyms, known terms, valid words, and
        # tokens glued to digits/symbols (d365, c++, node.js, python3).
        if (
            len(low) < 4
            or original.isupper()
            or low in _known
            or low in _sym.words
            or (s > 0 and (text_[s - 1].isdigit() or text_[s - 1] in "+#"))
            or (e < len(text_) and (text_[e].isdigit() or text_[e] in "+#."))
        ):
            return original

        max_dist = 1 if len(low) <= 5 else 2
        hits = _sym.lookup(
            low, Verbosity.TOP, max_edit_distance=max_dist, include_unknown=True
        )
        best = hits[0].term if hits else low

        if best == low and fallback:
            best = fallback(low) or low

        if best == low:
            return original

        changed = True
        return _restore_case(original, best)

    suggestion = WORD_RE.sub(fix, query)
    if changed and suggestion.casefold() != query.casefold():
        return suggestion
    return None