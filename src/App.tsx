import { useEffect, useRef, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/search";
const SPELLING_CHECK_URL = "http://127.0.0.1:8000/search/suggestion";
const RESUME_API_URL = "http://127.0.0.1:8000/candidates";

type MatchedSkill = {
  skill: string;
  last_used?: string | null;
  total_months?: number;
};

type ExperienceTimelineEntry = {
  role?: string | null;
  company?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  duration_months?: number | null;
  description?: string | null;
};

type ProjectEntry = {
  title: string;
  description?: string | null;
  url?: string | null;
  skills?: string[];
};

type EducationEntry = {
  institution?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  start_date?: string | null;
  end_date?: string | null;
};

type BackendMatchedSkill =
  | string
  | {
      skill?: string;
      last_used?: string | null;
      last_used_date?: string | null;
      total_months?: number;
    };

type Evidence = {
  source?: string;
  experience_id?: number;
  evidence_type?: string;
  requirement?: string;
  source_id?: number | string | null;
  evidence_id?: number | string | null;
  resume_id?: number | null;
  resume_section_id?: number | null;
  section_type?: string | null;
  section_title?: string | null;
  text?: string;
  similarity?: number;
  reranker_score?: number;
};

type MatchedRequirement = {
  type: string;
  requirement_types?: string[];
  requirement: string;
  matched: boolean;
  mandatory?: boolean;
  match_mode?: "HARD" | "SOFT";
  status?: "MATCH" | "PARTIAL_MATCH" | "NO_MATCH";
  candidate_value?: string | number | null;
  evidence?: Evidence[];
};

type BackendExplanation = string;

type BackendCandidate = {
  id?: number;
  name?: string;
  email?: string | null;
  phone?: string | null;
  score?: number;
  match_score?: number;
  match_status?: "MATCH" | "PARTIAL_MATCH" | "NO_MATCH" | string;
  headline?: string | null;
  location?: string | null;
  summary?: string | null;
  total_experience_months?: number;
  experience_timeline?: ExperienceTimelineEntry[];
  education?: EducationEntry[];
  profile_skills?: string[];
  projects?: ProjectEntry[];
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;

  candidate?: {
    id?: number;
    name?: string;
    email?: string | null;
    phone?: string | null;
    headline?: string | null;
    location?: string | null;
    summary?: string | null;
    total_experience_months?: number;
  };

  matched_skills?: BackendMatchedSkill[];
  evidence?: Evidence[];
  matched_requirements?: MatchedRequirement[];
  explanation?: BackendExplanation[];

  skill?: string;
  last_used_date?: string | null;
  last_used?: string | null;
  total_months?: number;

  semantic_validation?: {
    matched?: boolean;
    confidence?: number;
    reason?: string;
  };
};

type Candidate = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  score: number;
  headline: string | null;
  location: string | null;
  summary: string | null;
  total_experience_months?: number;
  experience_timeline: ExperienceTimelineEntry[];
  education: EducationEntry[];
  profile_skills: string[];
  projects: ProjectEntry[];
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  matched_skills: MatchedSkill[];
  evidence: Evidence[];
  matched_requirements: MatchedRequirement[];
  explanation: BackendExplanation[];
  match_status?: string;
};

type StructuredRequirements = {
  skills: string[];
  roles?: string[];
  companies?: string[];
  location?: string | null;
  role?: string | null;
  recency_months: number | null;
  experience_min_years: number | null;
  experience_max_years?: number | null;
  relevant_experience_min_years?: number | null;
  experience_scope?: string | null;
};

type RoutingPacket = {
  original_query: string;
  requested_count: number;
  count_explicit: boolean;
  structured_requirements: StructuredRequirements;
  semantic_requirement: string | null;
  semantic_requirements?: string[];
  requirements?: Array<{
    id?: string;
    original_text?: string;
    type?: string;
    mandatory?: boolean;
    match_mode?: "HARD" | "SOFT";
    canonical_value?: string | null;
    equivalent_terms?: string[];
    confidence?: number | null;
    temporal_window_months?: number | null;
  }>;
  assumptions?: string[];
  exclusions?: unknown[];
};

type SearchResponse = {
  route: string;
  search_id?: string;
  suggested_query?: string | null;
  search_specification?: Record<string, unknown>;
  parsed: RoutingPacket;
  results: Candidate[];
  message?: string | null;
  valid?: boolean;
  errors?: string[];
};

type BackendSearchResponse = Omit<SearchResponse, "results"> & {
  results: BackendCandidate[];
};

function getInitials(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (parts.length === 0) {
    return "?";
  }

  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function formatMonths(
  months?: number
): string {
  if (
    months === undefined ||
    months === null ||
    Number.isNaN(months)
  ) {
    return "Unknown";
  }

  if (months < 12) {
    return `${months} month${months === 1 ? "" : "s"}`;
  }

  const years = Math.floor(months / 12);
  const remainingMonths = months % 12;

  if (remainingMonths === 0) {
    return `${years} year${years === 1 ? "" : "s"}`;
  }

  return `${years}y ${remainingMonths}m`;
}

function formatTimelineDate(dateString?: string | null): string {
  if (!dateString) return "Date not listed";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return dateString;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function normalizeExternalUrl(value?: string | null): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;

  const candidate = /^[a-z][a-z\d+.-]*:/i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;
  try {
    const url = new URL(candidate);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}

type SeniorityBand = "Entry" | "Mid" | "Senior" | "Not specified";

const SENIORITY_BANDS: SeniorityBand[] = [
  "Entry",
  "Mid",
  "Senior",
  "Not specified",
];

function candidateSeniority(candidate: Candidate): SeniorityBand {
  const months = candidate.total_experience_months;
  if (months === undefined || months === null) return "Not specified";
  if (months < 36) return "Entry";
  if (months < 96) return "Mid";
  return "Senior";
}

function candidateRoleValues(candidate: Candidate): string[] {
  const primaryRole =
    candidate.experience_timeline.find((item) => item.is_current)?.role ??
    candidate.experience_timeline[0]?.role ??
    candidate.headline;
  return primaryRole?.trim() ? [primaryRole.trim()] : [];
}

function candidateSkillValues(candidate: Candidate): string[] {
  return [...new Set([
    ...candidate.profile_skills,
    ...candidate.matched_skills.map((item) => item.skill),
  ].map((skill) => skill.trim()).filter(Boolean))];
}

function groupMatchedRequirements(
  matches: MatchedRequirement[]
): MatchedRequirement[] {
  const grouped = new Map<string, MatchedRequirement>();
  for (const match of matches) {
    const key = match.requirement.trim().toLocaleLowerCase().replace(/\s+/g, " ");
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        ...match,
        requirement_types: [match.type.toLowerCase()],
        evidence: [...(match.evidence ?? [])],
      });
      continue;
    }
    existing.requirement_types = [...new Set([
      ...(existing.requirement_types ?? [existing.type.toLowerCase()]),
      match.type.toLowerCase(),
    ])];
    if (match.type.toLowerCase() === "skill") {
      existing.type = "skill";
      existing.candidate_value = match.candidate_value ?? existing.candidate_value;
    }
    existing.matched = existing.matched && match.matched;
    existing.evidence = [...(existing.evidence ?? []), ...(match.evidence ?? [])];
    if (existing.candidate_value == null && match.candidate_value != null) {
      existing.candidate_value = match.candidate_value;
    }
  }
  return [...grouped.values()];
}

function conciseEvidenceText(text: string, requirement: string): string {
  const sentences = text
    .split(/\r?\n+|(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  if (sentences.length <= 1) return text;

  const terms = requirement.toLowerCase().match(/[a-z0-9+#.]+/g) ?? [];
  const ranked = sentences.map((sentence) => {
    const lower = sentence.toLowerCase();
    const score = terms.filter((term) => lower.includes(term)).length;
    return { sentence, score };
  }).sort((left, right) => right.score - left.score || left.sentence.length - right.sentence.length);
  const best = ranked.find((item) => item.score > 0)?.sentence ?? sentences[0];
  return best.length > 360 ? `${best.slice(0, 357).trimEnd()}…` : best;
}

function evidenceSectionLabel(evidence: Evidence): string {
  const type = (evidence.section_type || evidence.evidence_type || "").trim().toLowerCase();
  if (type.includes("project")) return "Project";
  if (type.includes("experience") || type.includes("work")) return "Experience";
  if (type.includes("summary") || type.includes("profile")) return "Summary";
  if (type.includes("education")) return "Education";
  if (type.includes("skill")) return "Skills";
  if (evidence.section_title?.trim()) return evidence.section_title.trim();
  return "Resume section";
}

function normalizeCandidate(
  raw: BackendCandidate
): Candidate | null {
  const nestedCandidate =
    raw.candidate ?? {};

  const id =
    raw.id ??
    nestedCandidate.id;

  const name =
    raw.name ??
    nestedCandidate.name;

  if (
    id === undefined ||
    !name
  ) {
    return null;
  }

  const email =
    raw.email ??
    nestedCandidate.email ??
    null;

  let score =
    raw.match_score ??
    raw.score;

  if (
    score === undefined ||
    score === null ||
    Number.isNaN(Number(score))
  ) {
    score = 0;
  }

  /*
   * The backend can return matched_skills in more than
   * one shape. Structured results currently return skill
   * names as strings, while other result shapes may return
   * objects. Normalize both forms here so the renderer never
   * tries to read skill.skill from a string.
   */
  const rawMatchedSkills =
    Array.isArray(raw.matched_skills)
      ? raw.matched_skills
      : [];

  const matchedSkills: MatchedSkill[] =
    rawMatchedSkills.flatMap((item): MatchedSkill[] => {
        if (typeof item === "string") {
          const isPrimarySkill =
            raw.skill &&
            item.toLowerCase() ===
              raw.skill.toLowerCase();

          return [{
            skill: item,
            last_used: isPrimarySkill
              ? raw.last_used_date ??
                raw.last_used ??
                null
              : null,
            total_months: isPrimarySkill
              ? raw.total_months ??
                undefined
              : undefined,
          }];
        }

        if (
          !item ||
          typeof item !== "object" ||
          !item.skill
        ) {
          return [];
        }

        return [{
          skill: item.skill,
          last_used:
            item.last_used_date ??
            item.last_used ??
            null,
          total_months:
            item.total_months,
        }];
      });

  /*
   * Some structured responses expose only the primary
   * skill through `skill`. Add it if the matched_skills
   * array did not already contain it.
   */
  if (
    raw.skill &&
    !matchedSkills.some(
      (item) =>
        item.skill.toLowerCase() ===
        raw.skill!.toLowerCase()
    )
  ) {
    matchedSkills.push({
      skill: raw.skill,
      last_used:
        raw.last_used_date ??
        raw.last_used ??
        null,
      total_months:
        raw.total_months ??
        undefined,
    });
  }

  const evidence: Evidence[] =
    Array.isArray(raw.evidence)
      ? raw.evidence.filter(
          (item) =>
            item &&
            typeof item === "object"
        )
      : [];

  return {
    id: Number(id),
    name,
    email,
    phone: raw.phone ?? nestedCandidate.phone ?? null,
    score: Number(score),
    headline: raw.headline ?? nestedCandidate.headline ?? null,
    location: raw.location ?? nestedCandidate.location ?? null,
    summary: raw.summary ?? nestedCandidate.summary ?? null,
    total_experience_months:
      raw.total_experience_months ??
      nestedCandidate.total_experience_months,
    experience_timeline: Array.isArray(raw.experience_timeline)
      ? raw.experience_timeline
      : [],
    education: Array.isArray(raw.education) ? raw.education : [],
    profile_skills: Array.isArray(raw.profile_skills) ? raw.profile_skills : matchedSkills.map((item) => item.skill),
    projects: Array.isArray(raw.projects) ? raw.projects : [],
    linkedin_url: raw.linkedin_url ?? null,
    github_url: raw.github_url ?? null,
    portfolio_url: raw.portfolio_url ?? null,
    matched_skills: matchedSkills,
    evidence,
    matched_requirements: Array.isArray(raw.matched_requirements)
      ? raw.matched_requirements
      : [],
    explanation: Array.isArray(raw.explanation)
      ? raw.explanation.filter((item): item is string => typeof item === "string")
      : [],
    match_status:
      raw.match_status,
  };
}

function App() {
  const [query, setQuery] = useState("");
  const [suggestedQuery, setSuggestedQuery] = useState<string | null>(null);
  const [data, setData] =
    useState<SearchResponse | null>(null);
  const [loading, setLoading] =
    useState(false);
  const [searchPhase, setSearchPhase] = useState<"checking" | "searching">("checking");
  const [apiStatus, setApiStatus] = useState<"checking" | "connected" | "offline">("checking");
  const [searchTime, setSearchTime] =
    useState<number | null>(null);
  const [error, setError] =
    useState<string | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<Candidate | null>(null);
  const [profileTab, setProfileTab] = useState<"overview" | "experience" | "projects" | "education" | "skills">("overview");
  const [selectedRoleFilters, setSelectedRoleFilters] = useState<string[]>([]);
  const [selectedSkillFilters, setSelectedSkillFilters] = useState<string[]>([]);
  const [selectedSeniorityFilters, setSelectedSeniorityFilters] = useState<SeniorityBand[]>([]);
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [roleFilterSearch, setRoleFilterSearch] = useState("");
  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [skillFilterSearch, setSkillFilterSearch] = useState("");
  const roleDropdownRef = useRef<HTMLDivElement | null>(null);
  const skillDropdownRef = useRef<HTMLDivElement | null>(null);

  function openProfile(candidate: Candidate) {
    console.info("[GenieHire] Candidate profile opened", {
      candidateId: candidate.id,
      experienceEntries: candidate.experience_timeline.length,
      educationEntries: candidate.education.length,
      skills: candidate.profile_skills.length,
      projects: candidate.projects.length,
    });
    setSelectedProfile(candidate);
    setProfileTab("overview");
  }

  useEffect(() => {
    if (!selectedProfile) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedProfile(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [selectedProfile]);

  useEffect(() => {
    if (!roleDropdownOpen && !skillDropdownOpen) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !roleDropdownRef.current?.contains(target) &&
        !skillDropdownRef.current?.contains(target)
      ) {
        setRoleDropdownOpen(false);
        setSkillDropdownOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setRoleDropdownOpen(false);
        setSkillDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [roleDropdownOpen, skillDropdownOpen]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("http://127.0.0.1:8000/health", { signal: controller.signal })
      .then((response) => setApiStatus(response.ok ? "connected" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setApiStatus("offline");
      });
    return () => controller.abort();
  }, []);

  async function handleSearch(searchText = query, skipSpellingCheck = false) {
    if (
      !searchText.trim() ||
      loading
    ) {
      return;
    }

    setData(null);
    setError(null);
    setSuggestedQuery(null);
    setSearchTime(null);
    setSelectedRoleFilters([]);
    setSelectedSkillFilters([]);
    setSelectedSeniorityFilters([]);
    setRoleDropdownOpen(false);
    setRoleFilterSearch("");
    setSkillDropdownOpen(false);
    setSkillFilterSearch("");
    setLoading(true);
    setSearchPhase(skipSpellingCheck ? "searching" : "checking");

    const startTime =
      performance.now();
    const controller = new AbortController();
    // Allow the parser and first-use reranker model to finish on slower
    // machines while keeping a hard stop for genuinely stalled requests.
    const timeoutId = window.setTimeout(() => controller.abort(), 90000);
    console.info("[GenieHire] Search started", {
      queryChars: searchText.trim().length,
    });

    try {
      if (!skipSpellingCheck) {
        const spellingResponse = await fetch(SPELLING_CHECK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ query: searchText.trim() }),
        });
        if (!spellingResponse.ok) {
          throw new Error(`Spelling check failed (${spellingResponse.status})`);
        }
        const spellingResult: { suggested_query?: string | null } = await spellingResponse.json();
        const correction = spellingResult.suggested_query?.trim();
        if (correction && correction.toLocaleLowerCase() !== searchText.trim().toLocaleLowerCase()) {
          setSuggestedQuery(correction);
          return;
        }
      }

      setSuggestedQuery(null);
      setSearchPhase("searching");
      const res = await fetch(
        API_URL,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          signal: controller.signal,
          body: JSON.stringify({
            query: searchText.trim(),
          }),
        }
      );
      setApiStatus("connected");

      if (!res.ok) {
        throw new Error(
          `Server error (${res.status})`
        );
      }

      const response: BackendSearchResponse =
        await res.json();

      const endTime =
        performance.now();

      setSearchTime(
        Number(
          (
            (endTime - startTime) /
            1000
          ).toFixed(3)
        )
      );
      console.info("[GenieHire] Search response received", {
        searchId: response.search_id,
        route: response.route,
        candidates: Array.isArray(response.results) ? response.results.length : 0,
        durationSeconds: ((endTime - startTime) / 1000).toFixed(3),
      });

      if (
        response.valid === false
      ) {
        setError(
          response.errors?.join(
            ", "
          ) ||
            "Invalid query"
        );

        setData(null);
        return;
      }

      /*
       * Normalize the backend response
       * before rendering.
       *
       * This prevents the UI from crashing
       * when structured results contain:
       *
       * {
       *   candidate: {...},
       *   skill: "...",
       *   total_months: ...
       * }
       *
       * or semantic results contain:
       *
       * {
       *   id: ...,
       *   evidence: [...]
       * }
       */
      const normalizedResults =
        Array.isArray(response.results)
          ? response.results
              .map(
                normalizeCandidate
              )
              .filter(
                (
                  candidate
                ): candidate is Candidate =>
                  candidate !== null && candidate.match_status !== "NO_MATCH"
              )
          : [];

      setData({
        ...response,
        results:
          normalizedResults,
      });
    } catch (e) {
      const endTime =
        performance.now();
      if (e instanceof TypeError) setApiStatus("offline");

      setSearchTime(
        Number(
          (
            (endTime - startTime) /
            1000
          ).toFixed(3)
        )
      );

      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "Search is taking longer than expected. Please try again shortly."
          : e instanceof Error
            ? e.message
            : "Something went wrong. Is the backend running?"
      );
      console.warn("[GenieHire] Search failed", {
        durationSeconds: ((endTime - startTime) / 1000).toFixed(3),
        error: e instanceof Error ? e.message : "Unknown error",
      });

      setData(null);
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  async function handleViewResume(
    candidateId: number
  ) {
    console.info("[GenieHire] Resume request started", { candidateId });
    try {
      const response =
        await fetch(
          `${RESUME_API_URL}/${candidateId}/resume`
        );

      if (!response.ok) {
        throw new Error(
          `Unable to fetch resume (${response.status})`
        );
      }

      const resumeData: {
        candidate_id: number;
        resume_url: string;
      } = await response.json();

      window.open(
        resumeData.resume_url,
        "_blank",
        "noopener,noreferrer"
      );
      console.info("[GenieHire] Resume opened", { candidateId });
    } catch (e) {
      console.error("[GenieHire] Resume request failed", {
        candidateId,
        error: e instanceof Error ? e.message : "Unknown error",
      });
      setError(
        e instanceof Error
          ? e.message
          : "Unable to open resume"
      );
    }
  }

  const requirements =
    data?.parsed
      ?.structured_requirements;
  const semanticCriteriaRaw = data?.parsed.requirements
    ?.filter((item) => item.type?.toUpperCase() === "SEMANTIC" && item.mandatory !== false)
    .map((item) => item.original_text?.trim())
    .filter((item): item is string => Boolean(item))
    ?? data?.parsed.semantic_requirements
    ?? (data?.parsed.semantic_requirement ? [data.parsed.semantic_requirement] : []);
  const semanticCriteria = [...new Map(
    semanticCriteriaRaw.map((item) => [item.trim().toLocaleLowerCase(), item.trim()])
  ).values()];
  const temporalCriteria = data?.parsed.requirements?.filter(
    (item) => item.type?.toUpperCase() === "TEMPORAL" && item.temporal_window_months != null,
  ) ?? [];
  const resultCount =
    data?.results.length ?? 0;
  const availableRoles = [...new Map(
    (data?.results ?? [])
      .flatMap(candidateRoleValues)
      .map((role) => [role.toLocaleLowerCase(), role] as const)
  ).values()].sort((left, right) => left.localeCompare(right));
  const visibleRoleOptions = availableRoles.filter((role) =>
    roleFilterSearch.trim().length >= 2 &&
    role.toLocaleLowerCase().includes(roleFilterSearch.trim().toLocaleLowerCase())
  );
  const availableSkills = [...new Map(
    (data?.results ?? [])
      .flatMap(candidateSkillValues)
      .map((skill) => [skill.toLocaleLowerCase(), skill] as const)
  ).values()].sort((left, right) => left.localeCompare(right));
  const visibleSkillOptions = availableSkills.filter((skill) =>
    skill.toLocaleLowerCase().includes(skillFilterSearch.trim().toLocaleLowerCase())
  );
  const availableSeniority = SENIORITY_BANDS.filter((band) =>
    (data?.results ?? []).some((candidate) => candidateSeniority(candidate) === band)
  );
  const hasActiveFilters = Boolean(
    selectedRoleFilters.length || selectedSkillFilters.length || selectedSeniorityFilters.length
  );
  const filteredResults = (data?.results ?? []).filter((candidate) => {
    const candidateRoles = candidateRoleValues(candidate).map((value) => value.toLocaleLowerCase());
    const candidateSkills = candidateSkillValues(candidate).map((value) => value.toLocaleLowerCase());
    const roleMatches = !selectedRoleFilters.length || selectedRoleFilters.some((role) =>
      candidateRoles.includes(role.toLocaleLowerCase())
    );
    const skillMatches = !selectedSkillFilters.length || selectedSkillFilters.some((skill) =>
      candidateSkills.includes(skill.toLocaleLowerCase())
    );
    const seniorityMatches = !selectedSeniorityFilters.length || selectedSeniorityFilters.includes(candidateSeniority(candidate));
    return roleMatches && skillMatches && seniorityMatches;
  });
  const profileLinkedInUrl = normalizeExternalUrl(selectedProfile?.linkedin_url);
  const profileGitHubUrl = normalizeExternalUrl(selectedProfile?.github_url);
  const profilePortfolioUrl = normalizeExternalUrl(selectedProfile?.portfolio_url);

  return (
    <div className={`app-shell${data && !loading ? " has-search-results" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            G
          </div>

          <div>
            <div className="brand-name">
              GenieHire
            </div>

            <div className="brand-subtitle">
              Recruiter Intelligence
            </div>
          </div>
        </div>

        <div className={`topbar-status is-${apiStatus}`} role="status" aria-live="polite">
          <span className="status-dot" />
          {apiStatus === "checking" ? "Checking database…" : apiStatus === "connected" ? "Talent database connected" : "Database unavailable"}
        </div>
      </header>

      <main className="main-content">
        <section className="hero">
          <div className="hero-eyebrow">
            CANDIDATE SOURCING
          </div>

          <h1>
            Find the right
            <span> candidates.</span>
          </h1>

          <p className="hero-description">
            Search your talent database
            using natural language.
            Describe the experience,
            skills, or background you
            need.
          </p>

          <form
            className="search-container"
            onSubmit={(event) => {
              event.preventDefault();
              void handleSearch();
            }}
          >
            <div className="search-icon">
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d="m21 21-4.35-4.35m1.35-5.65a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </div>

            <input
              value={query}
              onChange={(e) =>
                {
                  setQuery(e.target.value);
                  setSuggestedQuery(null);
                }
              }
              placeholder="e.g. Find Python developers with 5+ years of experience"
              aria-label="Candidate search"
            />

            <button
              type="submit"
              className="search-button"
              disabled={
                loading ||
                !query.trim()
              }
            >
              {loading ? (
                <>
                  <span className="button-spinner" />
                  Searching
                </>
              ) : (
                <>
                  Search
                  <span className="button-arrow">
                    →
                  </span>
                </>
              )}
            </button>
          </form>

          {suggestedQuery && (
            <div className="spelling-suggestion">
              <span>Check this spelling before searching:</span>
              <button
                className="spelling-suggestion-correction"
                type="button"
                onClick={() => {
                  setQuery(suggestedQuery);
                  void handleSearch(suggestedQuery, true);
                }}
              >
                Search “{suggestedQuery}”
              </button>
              <button
                className="spelling-suggestion-original"
                type="button"
                onClick={() => void handleSearch(query, true)}
              >
                Search as typed
              </button>
            </div>
          )}

          <div className="search-examples">
            <span>Try:</span>

            <button
              onClick={() =>
                setQuery(
                  "Find Python developers with 5+ years of experience"
                )
              }
            >
              Python developers
            </button>

            <button
              onClick={() =>
                setQuery(
                  "Find candidates with experience in financial transformation"
                )
              }
            >
              Financial transformation
            </button>

            <button
              onClick={() =>
                setQuery(
                  "Find React and Node.js developers"
                )
              }
            >
              React + Node.js
            </button>

            <button
              onClick={() =>
                setQuery(
                  "Find Python developers in Pune with 3+ years who have built AI products"
                )
              }
            >
              Python + AI + Pune
            </button>
          </div>

          <div className="search-capabilities" aria-label="Search supports">
            <span>Search across</span>
            <span>Roles and skills</span>
            <span>Projects and work history</span>
            <span>Location and experience</span>
          </div>
        </section>

        {error && (
          <div className="alert error-alert">
            <div className="alert-icon">
              !
            </div>

            <div>
              <strong>
                Search failed
              </strong>

              <p>{error}</p>
            </div>
          </div>
        )}

        {loading && (
          <section className="loading-state">
            <div className="loading-spinner" />

            <div>
              <strong>{searchPhase === "checking" ? "Checking query spelling" : "Searching your talent database"}</strong>

              <p>
                {searchPhase === "checking"
                  ? "Checking for likely spelling mistakes before searching..."
                  : "Finding candidates that match your requirements..."}
              </p>
            </div>
          </section>
        )}

        {data &&
          !loading && (
            <section className="results-section">
              <div className="results-header">
                <div>
                  <div className="results-title-row">
                    <h2>
                      Search results
                    </h2>

                    <span className="result-count">
                      {resultCount}{" "}
                      {resultCount ===
                      1
                        ? "candidate"
                        : "candidates"}
                    </span>
                  </div>

                  <div className="query-display">
                    “
                    {
                      data.parsed
                        .original_query
                    }
                    ”
                  </div>
                </div>

                <div className="search-meta">
                  {searchTime !==
                    null && (
                    <span>
                      {
                        searchTime
                      }
                      s
                    </span>
                  )}

                  <span className="route-badge">
                    <span className="route-dot" />
                    {data.route}
                  </span>
                </div>
              </div>

              <div className="requirement-bar" aria-label="Interpreted search criteria">
                <span className="criteria-heading">Search criteria</span>
                {requirements?.skills?.map(
                  (skill) => (
                    <span
                      className="requirement-pill"
                      key={skill}
                    >
                      {skill}
                    </span>
                  )
                )}

                {(requirements?.experience_min_years != null || requirements?.experience_max_years != null) && (
                    <span className="requirement-pill">
                      {requirements.experience_min_years != null && requirements.experience_max_years != null
                        ? `${requirements.experience_min_years}–${requirements.experience_max_years} years experience`
                        : requirements.experience_min_years != null
                          ? `${requirements.experience_min_years}+ years experience`
                          : `Up to ${requirements.experience_max_years} years experience`}
                    </span>
                  )}

                {requirements?.relevant_experience_min_years !== null &&
                  requirements?.relevant_experience_min_years !== undefined && (
                    <span className="requirement-pill">
                      {requirements.relevant_experience_min_years}+ years relevant experience
                    </span>
                  )}

                {temporalCriteria.map((item, index) => {
                  const months = item.temporal_window_months!;
                  const inferred = (item.confidence ?? 1) < 0.75;
                  return (
                    <span className="requirement-pill" key={`temporal-${item.id ?? index}`}>
                      Recent activity · {inferred ? "assumed " : "last "}{months} {months === 1 ? "month" : "months"}
                    </span>
                  );
                })}

                {(requirements?.roles ?? (requirements?.role ? [requirements.role] : [])).map((role) => (
                  <span className="requirement-pill" key={`role-${role}`}>{role}</span>
                ))}

                {requirements?.companies?.map((company) => (
                  <span className="requirement-pill" key={`company-${company}`}>{company}</span>
                ))}

                {requirements?.location && (
                  <span className="requirement-pill">
                    {requirements.location}
                  </span>
                )}

                {semanticCriteria.map((semantic) => (
                  <span className="requirement-pill semantic-pill" key={`semantic-${semantic}`}>{semantic}</span>
                ))}
              </div>

              {data.parsed.assumptions && data.parsed.assumptions.length > 0 && (
                <div className="assumption-info">
                  <strong>Search assumptions</strong>
                  {data.parsed.assumptions.map((assumption) => (
                    <span key={assumption}>{assumption}</span>
                  ))}
                </div>
              )}

              {data.message && (
                <div className="result-message">
                  <span className="message-icon">
                    ✓
                  </span>

                  <span>
                    {data.message}
                  </span>
                </div>
              )}

              {data.route ===
                "HYBRID" && (
                <div className="hybrid-info">
                  <span className="hybrid-icon">
                    ✦
                  </span>

                  <span>
                    Structured requirements
                    and semantic relevance
                    were both used for
                    this search.
                  </span>
                </div>
              )}

              {resultCount > 0 ? (
                <div className="results-content-grid">
                  <aside className="result-filter-panel" aria-label="Filter search results">
                    <div className="filter-panel-heading">
                      <div>
                        <h3>Filters</h3>
                        <span>{filteredResults.length} of {resultCount} shown</span>
                      </div>
                      {hasActiveFilters && (
                        <button
                          className="filter-clear-button"
                          type="button"
                          onClick={() => {
                            setSelectedRoleFilters([]);
                            setSelectedSkillFilters([]);
                            setSelectedSeniorityFilters([]);
                            setRoleDropdownOpen(false);
                            setSkillDropdownOpen(false);
                            setRoleFilterSearch("");
                            setSkillFilterSearch("");
                          }}
                        >
                          Clear
                        </button>
                      )}
                    </div>

                    <p className="filter-scope-note">Filters apply to the candidates returned for this search.</p>

                    <fieldset className="filter-group">
                      <legend>Role</legend>
                      {availableRoles.length ? (
                        <div className="filter-dropdown" ref={roleDropdownRef}>
                          <button
                            className={`filter-dropdown-trigger${roleDropdownOpen ? " is-open" : ""}`}
                            type="button"
                            aria-expanded={roleDropdownOpen}
                            aria-controls="role-filter-options"
                            onClick={() => {
                              setRoleDropdownOpen((open) => !open);
                              setSkillDropdownOpen(false);
                            }}
                          >
                            <span>
                              {selectedRoleFilters.length
                                ? `${selectedRoleFilters.length} role${selectedRoleFilters.length === 1 ? "" : "s"} selected`
                                : "Select roles"}
                            </span>
                            <span className="filter-dropdown-chevron" aria-hidden="true">⌄</span>
                          </button>
                          {roleDropdownOpen && (
                            <div className="filter-dropdown-menu" id="role-filter-options">
                              <input
                                className="filter-dropdown-search"
                                type="search"
                                value={roleFilterSearch}
                                onChange={(event) => setRoleFilterSearch(event.target.value)}
                                placeholder="Search role titles"
                                aria-label="Search available roles"
                              />
                              <div className="filter-dropdown-options">
                                {roleFilterSearch.trim().length < 2 ? (
                                  <span className="filter-unavailable">Type at least 2 characters to see title suggestions</span>
                                ) : visibleRoleOptions.length ? visibleRoleOptions.map((role) => (
                                  <label className="filter-option" key={role}>
                                    <input
                                      type="checkbox"
                                      checked={selectedRoleFilters.includes(role)}
                                      onChange={() => setSelectedRoleFilters((current) =>
                                        current.includes(role)
                                          ? current.filter((item) => item !== role)
                                          : [...current, role]
                                      )}
                                    />
                                    <span>{role}</span>
                                  </label>
                                )) : (
                                  <span className="filter-unavailable">No roles match this search</span>
                                )}
                              </div>
                              {selectedRoleFilters.length > 0 && (
                                <button
                                  className="filter-dropdown-clear"
                                  type="button"
                                  onClick={() => setSelectedRoleFilters([])}
                                >
                                  Clear selected roles
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      ) : <span className="filter-unavailable">No role data in these results</span>}
                    </fieldset>

                    <fieldset className="filter-group">
                      <legend>Skills</legend>
                      {availableSkills.length ? (
                        <div className="filter-dropdown" ref={skillDropdownRef}>
                          <button
                            className={`filter-dropdown-trigger${skillDropdownOpen ? " is-open" : ""}`}
                            type="button"
                            aria-expanded={skillDropdownOpen}
                            aria-controls="skill-filter-options"
                            onClick={() => {
                              setSkillDropdownOpen((open) => !open);
                              setRoleDropdownOpen(false);
                            }}
                          >
                            <span>
                              {selectedSkillFilters.length
                                ? `${selectedSkillFilters.length} skill${selectedSkillFilters.length === 1 ? "" : "s"} selected`
                                : "Select skills"}
                            </span>
                            <span className="filter-dropdown-chevron" aria-hidden="true">⌄</span>
                          </button>
                          {skillDropdownOpen && (
                            <div className="filter-dropdown-menu" id="skill-filter-options">
                              <input
                                className="filter-dropdown-search"
                                type="search"
                                value={skillFilterSearch}
                                onChange={(event) => setSkillFilterSearch(event.target.value)}
                                placeholder="Search skills"
                                aria-label="Search available skills"
                              />
                              <div className="filter-dropdown-options">
                                {visibleSkillOptions.length ? visibleSkillOptions.map((skill) => (
                                  <label className="filter-option" key={skill}>
                                    <input
                                      type="checkbox"
                                      checked={selectedSkillFilters.includes(skill)}
                                      onChange={() => setSelectedSkillFilters((current) =>
                                        current.includes(skill)
                                          ? current.filter((item) => item !== skill)
                                          : [...current, skill]
                                      )}
                                    />
                                    <span>{skill}</span>
                                  </label>
                                )) : (
                                  <span className="filter-unavailable">No skills match this search</span>
                                )}
                              </div>
                              {selectedSkillFilters.length > 0 && (
                                <button
                                  className="filter-dropdown-clear"
                                  type="button"
                                  onClick={() => setSelectedSkillFilters([])}
                                >
                                  Clear selected skills
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      ) : <span className="filter-unavailable">No skill data in these results</span>}
                    </fieldset>

                    <fieldset className="filter-group">
                      <legend>Seniority</legend>
                      <p className="filter-group-note">Based on total experience</p>
                      {availableSeniority.map((band) => (
                        <label className="filter-option" key={band}>
                          <input
                            type="checkbox"
                            checked={selectedSeniorityFilters.includes(band)}
                            onChange={() => setSelectedSeniorityFilters((current) =>
                              current.includes(band)
                                ? current.filter((item) => item !== band)
                                : [...current, band]
                            )}
                          />
                          <span>{band}{band === "Entry" ? " · 0–2 years" : band === "Mid" ? " · 3–7 years" : band === "Senior" ? " · 8+ years" : ""}</span>
                        </label>
                      ))}
                    </fieldset>
                  </aside>

                  <div className="results-list-column">
                    {filteredResults.length ? (
                      <div className="candidate-list">
                  {filteredResults.map(
                    (candidate) => {
                      const shownProofs = new Set<string>();
                      const displayedRequirements = groupMatchedRequirements(
                        candidate.matched_requirements
                      );
                      return (
                        <article
                          className="candidate-card"
                          key={
                            candidate.id
                          }
                        >
                          <div className="candidate-main">
                            <div className="avatar">
                              {getInitials(
                                candidate.name
                              )}
                            </div>

                            <div className="candidate-info">
                              <div className="candidate-name-row">
                                <h3>
                                  {
                                    candidate.name
                                  }
                                </h3>
                                {candidate.match_status && candidate.match_status !== "NO_MATCH" && (
                                  <span className={`candidate-match-status ${candidate.match_status === "PARTIAL_MATCH" ? "partial" : "complete"}`}>
                                    {candidate.match_status === "PARTIAL_MATCH" ? "Partial match" : "Match"}
                                  </span>
                                )}

                              </div>

                              {candidate.email && (
                                <div className="candidate-email">
                                  {
                                    candidate.email
                                  }
                                </div>
                              )}

                              {candidate.location && (
                                <div className="candidate-email">
                                  {candidate.location}
                                </div>
                              )}

                              {(candidate.headline ||
                                candidate.total_experience_months !== undefined) && (
                                <div className="candidate-email">
                                  {candidate.headline}
                                  {candidate.headline &&
                                    candidate.total_experience_months !== undefined &&
                                    " · "}
                                  {candidate.total_experience_months !== undefined &&
                                    `${formatMonths(candidate.total_experience_months)} experience`}
                                </div>
                              )}

                              {displayedRequirements.some((match) => match.matched) && (
                                <div className="evidence-preview">
                                  <div className="evidence-label">Why this candidate matches</div>
                                  {displayedRequirements
                                    .filter((match) => match.matched)
                                    .map((match, index) => {
                                      const profileProjectProofs: Evidence[] =
                                        match.requirement_types?.includes("skill")
                                          ? candidate.projects
                                              .filter((project) => {
                                                const requirement = match.requirement.trim().toLocaleLowerCase();
                                                return (project.skills ?? []).some((skill) =>
                                                  skill.trim().toLocaleLowerCase() === requirement
                                                ) || `${project.title} ${project.description ?? ""}`
                                                  .toLocaleLowerCase()
                                                  .includes(requirement);
                                              })
                                              .map((project, projectIndex) => ({
                                                evidence_type: "project",
                                                source_id: `profile-project-${projectIndex}`,
                                                source: project.title,
                                                text: project.description?.trim() || project.title,
                                              }))
                                          : [];
                                      const proofs = [...(match.evidence ?? []), ...profileProjectProofs]
                                        .filter((item) => item.text?.trim())
                                        .filter((item) => !(
                                          match.requirement_types?.includes("skill") &&
                                          ["skill", "skills"].includes((item.evidence_type ?? "").toLowerCase())
                                        ))
                                        .filter((item) => {
                                          const key = `${item.experience_id ?? item.source_id ?? item.evidence_id ?? ""}:${item.text}`;
                                          if (shownProofs.has(key)) return false;
                                          shownProofs.add(key);
                                          return true;
                                        });
                                      const visibleProofs = proofs.slice(0, 1);
                                      return (
                                        <div className="evidence-snippet" key={`${match.type}-${match.requirement}-${index}`}>
                                          <div className="evidence-snippet-meta">
                                            <span className="evidence-skill-tag">
                                              {match.type === "relevant_experience" ? "Relevant experience" : match.requirement}
                                            </span>
                                            {match.type !== "skill" && match.candidate_value !== undefined &&
                                              match.candidate_value !== null &&
                                              String(match.candidate_value).trim().toLowerCase() !== match.requirement.trim().toLowerCase() && (
                                              <span className="evidence-source">{String(match.candidate_value)}</span>
                                            )}
                                          </div>
                                          <div className="evidence-proof">
                                            {visibleProofs.map((proof, proofIndex) => (
                                              <p key={`${proof.source_id ?? proofIndex}`}>
                                                {proof.source ? (
                                                  <>
                                                    <strong>{evidenceSectionLabel(proof)} · {proof.source}: </strong>
                                                    {conciseEvidenceText(proof.text ?? "", match.requirement)}
                                                  </>
                                                ) : (
                                                  <>
                                                    <strong>{evidenceSectionLabel(proof)}: </strong>
                                                    {conciseEvidenceText(proof.text ?? "", match.requirement)}
                                                  </>
                                                )}
                                              </p>
                                            ))}
                                            {visibleProofs.length === 0 && (
                                              <p className="evidence-fallback">
                                                {match.type === "relevant_experience"
                                                  ? "Supporting activity appears in these dated roles; exact activity dates were not listed."
                                                  : match.type === "skill"
                                                    ? "Listed as a skill on the candidate profile; no supporting project or experience excerpt was available."
                                                    : match.candidate_value != null
                                                      ? `Candidate profile lists: ${match.candidate_value}`
                                                    : "Matched against structured candidate profile data."}
                                              </p>
                                            )}
                                          </div>
                                        </div>
                                      );
                                    })}
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="candidate-actions">
                            <button
                              className="resume-button"
                              onClick={() => openProfile(candidate)}
                            >
                              View profile
                              <span>
                                ↗
                              </span>
                            </button>
                          </div>
                        </article>
                      );
                    }
                  )}
                      </div>
                    ) : (
                      <div className="filter-empty-state">
                        <strong>No candidates match these filters</strong>
                        <p>Try removing a selection or clear the filters to see all {resultCount} returned candidates.</p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">
                    ⌕
                  </div>

                  <h3>
                    No candidates found
                  </h3>

                  <p>
                    {requirements?.relevant_experience_min_years &&
                    data.parsed.semantic_requirement
                      ? `No candidates had at least ${requirements.relevant_experience_min_years} years of dated experience supporting “${data.parsed.semantic_requirement}”. Try lowering the relevant-experience requirement or broadening the activity.`
                      : "Try changing your search criteria or using broader requirements."}
                  </p>
                </div>
              )}
            </section>
          )}
      </main>

      {selectedProfile && (
        <div className="profile-backdrop" onMouseDown={() => setSelectedProfile(null)}>
          <aside
            className="profile-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="profile-name"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setSelectedProfile(null);
            }}
          >
            <div className="profile-panel-topbar">
              <span>Candidate profile</span>
              <button className="profile-close" onClick={() => setSelectedProfile(null)} aria-label="Close profile">×</button>
            </div>
            <header className="profile-header">
              <div className="avatar">{getInitials(selectedProfile.name)}</div>
              <div className="profile-heading">
                <h2 id="profile-name">{selectedProfile.name}</h2>
                {selectedProfile.headline && <p>{selectedProfile.headline}</p>}
                {selectedProfile.location && <p>{selectedProfile.location}</p>}
              </div>
            </header>
            <div className="profile-links">
              {profileLinkedInUrl && <a href={profileLinkedInUrl} target="_blank" rel="noopener noreferrer">LinkedIn ↗</a>}
              {profileGitHubUrl && <a href={profileGitHubUrl} target="_blank" rel="noopener noreferrer">GitHub ↗</a>}
              {profilePortfolioUrl && <a href={profilePortfolioUrl} target="_blank" rel="noopener noreferrer">Portfolio ↗</a>}
              <button className="profile-resume-button" onClick={() => void handleViewResume(selectedProfile.id)}>View resume ↗</button>
            </div>
            <nav className="profile-tabs" aria-label="Candidate profile sections">
              {(["overview", "experience", "projects", "education", "skills"] as const).map((tab) => (
                <button key={tab} className={profileTab === tab ? "active" : ""} onClick={() => setProfileTab(tab)}>
                  {tab[0].toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </nav>
            <div className="profile-content">
              {profileTab === "overview" && (
                <>
                  <section className="profile-section">
                    <h3>Contact</h3>
                    {selectedProfile.email && <p><span>Email</span><a href={`mailto:${selectedProfile.email}`}>{selectedProfile.email}</a></p>}
                    {selectedProfile.phone && <p><span>Phone</span><a href={`tel:${selectedProfile.phone}`}>{selectedProfile.phone}</a></p>}
                    {!selectedProfile.email && !selectedProfile.phone && <p className="profile-muted">No contact details available.</p>}
                  </section>
                  {selectedProfile.summary && <section className="profile-section"><h3>Summary</h3><p className="profile-summary">{selectedProfile.summary}</p></section>}
                  <section className="profile-section">
                    <h3>Search match</h3>
                    {selectedProfile.matched_requirements.filter((item) => item.matched).map((item, index) => (
                      <div className="profile-match" key={`${item.requirement}-${index}`}>
                        <span>{item.requirement}</span>
                        <p>{item.evidence?.find((proof) => proof.text)?.text ?? item.candidate_value ?? "Matched candidate profile"}</p>
                      </div>
                    ))}
                  </section>
                </>
              )}
              {profileTab === "experience" && (
                <section className="profile-section">
                  <h3>Experience{selectedProfile.total_experience_months !== undefined ? ` · ${formatMonths(selectedProfile.total_experience_months)} total` : ""}</h3>
                  {selectedProfile.experience_timeline.length ? selectedProfile.experience_timeline.map((item, index) => (
                    <article className="profile-entry" key={`${item.role}-${item.company}-${index}`}>
                      <strong>{item.role ?? "Role not listed"}</strong>
                      <p>{item.company ?? "Company not listed"}</p>
                      <span>{formatTimelineDate(item.start_date)} – {item.is_current ? "Present" : formatTimelineDate(item.end_date)}</span>
                      {item.description && <p className="profile-entry-description">{item.description}</p>}
                    </article>
                  )) : <p className="profile-muted">No experience history available.</p>}
                </section>
              )}
              {profileTab === "projects" && (
                <section className="profile-section">
                  <h3>Projects</h3>
                  {selectedProfile.projects.length ? selectedProfile.projects.map((project, index) => (
                    <article className="profile-entry" key={`${project.title}-${index}`}>
                      <strong>{project.title}</strong>
                      {project.description && <p className="profile-entry-description">{project.description}</p>}
                      {project.skills && project.skills.length > 0 && <div className="profile-entry-skills">{project.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
                      {project.url && normalizeExternalUrl(project.url) && <a className="profile-project-link" href={normalizeExternalUrl(project.url) ?? undefined} target="_blank" rel="noopener noreferrer">Open project ↗</a>}
                    </article>
                  )) : <p className="profile-muted">No project details available.</p>}
                </section>
              )}
              {profileTab === "education" && (
                <section className="profile-section">
                  <h3>Education</h3>
                  {selectedProfile.education.length ? selectedProfile.education.map((item, index) => (
                    <article className="profile-entry" key={`${item.institution}-${item.degree}-${index}`}>
                      <strong>{item.degree ?? item.field_of_study ?? "Education"}</strong>
                      <p>{item.institution ?? "Institution not listed"}</p>
                      {(item.start_date || item.end_date) && <span>{formatTimelineDate(item.start_date)} – {formatTimelineDate(item.end_date)}</span>}
                    </article>
                  )) : <p className="profile-muted">No education history available.</p>}
                </section>
              )}
              {profileTab === "skills" && (
                <section className="profile-section">
                  <h3>Skills</h3>
                  {selectedProfile.profile_skills.length ? <div className="profile-skill-list">{selectedProfile.profile_skills.map((skill) => <span key={skill}>{skill}</span>)}</div> : <p className="profile-muted">No skills available.</p>}
                </section>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
