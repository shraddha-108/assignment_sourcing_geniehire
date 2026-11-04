import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/search";
const SPELLING_CHECK_URL = "http://127.0.0.1:8000/search/suggestion";
const FILTER_SEARCH_URL = "http://127.0.0.1:8000/search/refine";
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

type MatchedExperience = {
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
  matched_experience?: MatchedExperience | null;
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
  matched_experience: MatchedExperience | null;
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

type SelectedLocation = {
  place_id: string;
  label: string;
  city: string | null;
  state: string | null;
  country: string | null;
};

type LocationSuggestion = {
  text: string;
  properties: any;
};

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
  if(months < 144) return "Senior";
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

function normalizeComparableText(value?: string | null): string {
  return (value ?? "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ");
}

function getMatchedExperience(
  raw: BackendCandidate,
  experienceTimeline: ExperienceTimelineEntry[],
  matchedRequirements: MatchedRequirement[]
): MatchedExperience | null {
  if (raw.matched_experience) {
    return raw.matched_experience;
  }

  const matched = matchedRequirements.filter(
    (item) => item.matched && item.status !== "NO_MATCH"
  );

  const roleMatch = matched.find(
    (item) =>
      item.type === "role" ||
      item.requirement_types?.includes("role")
  );

  const companyMatch = matched.find(
    (item) =>
      item.type === "company" ||
      item.requirement_types?.includes("company")
  );

  const requestedRole = normalizeComparableText(
    roleMatch?.candidate_value != null
      ? String(roleMatch.candidate_value)
      : roleMatch?.requirement
  );

  const requestedCompany = normalizeComparableText(
    companyMatch?.candidate_value != null
      ? String(companyMatch.candidate_value)
      : companyMatch?.requirement
  );

  if (!requestedRole && !requestedCompany) {
    return null;
  }

  const candidates = experienceTimeline.filter((experience) => {
    const role = normalizeComparableText(experience.role);
    const company = normalizeComparableText(experience.company);

    const roleMatches =
      !requestedRole || role === requestedRole;
    const companyMatches =
      !requestedCompany || company === requestedCompany;

    return roleMatches && companyMatches;
  });

  if (candidates.length === 0) {
    return null;
  }

  const sorted = [...candidates].sort((a, b) => {
    // Prefer the currently held matching experience.
    if (Boolean(a.is_current) !== Boolean(b.is_current)) {
      return a.is_current ? -1 : 1;
    }

    // If both are current/non-current, prefer the most recent start date.
    const aStart = a.start_date
      ? new Date(a.start_date).getTime()
      : Number.NEGATIVE_INFINITY;
    const bStart = b.start_date
      ? new Date(b.start_date).getTime()
      : Number.NEGATIVE_INFINITY;

    return bStart - aStart;
  });

  return sorted[0];
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

  const experienceTimeline: ExperienceTimelineEntry[] =
    Array.isArray(raw.experience_timeline)
      ? raw.experience_timeline
      : [];

  const matchedRequirements: MatchedRequirement[] =
    Array.isArray(raw.matched_requirements)
      ? raw.matched_requirements
      : [];

  const matchedExperience = getMatchedExperience(
    raw,
    experienceTimeline,
    matchedRequirements
  );

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
    experience_timeline: experienceTimeline,
    matched_experience: matchedExperience,
    education: Array.isArray(raw.education) ? raw.education : [],
    profile_skills: Array.isArray(raw.profile_skills) ? raw.profile_skills : matchedSkills.map((item) => item.skill),
    projects: Array.isArray(raw.projects) ? raw.projects : [],
    linkedin_url: raw.linkedin_url ?? null,
    github_url: raw.github_url ?? null,
    portfolio_url: raw.portfolio_url ?? null,
    matched_skills: matchedSkills,
    evidence,
    matched_requirements: matchedRequirements,
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
  const [selectedLocationFilters, setSelectedLocationFilters] = useState<SelectedLocation[]>([]);
  const [selectedCompanyFilters, setSelectedCompanyFilters] = useState<string[]>([]);
  const [selectedDomainFilters, setSelectedDomainFilters] = useState<string[]>([]);
  const [selectedMinExperience, setSelectedMinExperience] = useState<string>("");
  const [selectedMaxExperience, setSelectedMaxExperience] = useState<string>("");
  const [appliedRoleFilters, setAppliedRoleFilters] = useState<string[]>([]);
  const [appliedSkillFilters, setAppliedSkillFilters] = useState<string[]>([]);
  const [appliedSeniorityFilters, setAppliedSeniorityFilters] = useState<SeniorityBand[]>([]);
  const [appliedLocationFilters, setAppliedLocationFilters] = useState<SelectedLocation[]>([]);
  const [appliedCompanyFilters, setAppliedCompanyFilters] = useState<string[]>([]);
  const [appliedDomainFilters, setAppliedDomainFilters] = useState<string[]>([]);
  const [appliedMinExperience, setAppliedMinExperience] = useState<number | null>(null);
  const [appliedMaxExperience, setAppliedMaxExperience] = useState<number | null>(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [roleFilterSearch, setRoleFilterSearch] = useState("");
  const [skillFilterSearch, setSkillFilterSearch] = useState("");
  const [locationFilterSearch, setLocationFilterSearch] = useState("");
  const [locationSuggestions, setLocationSuggestions] = useState<LocationSuggestion[]>([]);
  const [locationSuggestionsLoading, setLocationSuggestionsLoading] = useState(false);
  const [locationAutocompleteError, setLocationAutocompleteError] = useState<string | null>(null);
  const [companyFilterSearch, setCompanyFilterSearch] = useState("");

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
    if (!filterPanelOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedRoleFilters(appliedRoleFilters);
        setSelectedSkillFilters(appliedSkillFilters);
        setSelectedSeniorityFilters(appliedSeniorityFilters);
        setSelectedLocationFilters(appliedLocationFilters);
        setSelectedCompanyFilters(appliedCompanyFilters);
        setSelectedDomainFilters(appliedDomainFilters);
        setSelectedMinExperience(appliedMinExperience === null ? "" : String(appliedMinExperience));
        setSelectedMaxExperience(appliedMaxExperience === null ? "" : String(appliedMaxExperience));
        setRoleFilterSearch("");
        setSkillFilterSearch("");
        setLocationFilterSearch("");
        setLocationSuggestions([]);
        setCompanyFilterSearch("");
        setFilterPanelOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [filterPanelOpen, appliedRoleFilters, appliedSkillFilters, appliedSeniorityFilters, appliedLocationFilters, appliedCompanyFilters, appliedDomainFilters, appliedMinExperience, appliedMaxExperience]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("http://127.0.0.1:8000/health", { signal: controller.signal })
      .then((response) => setApiStatus(response.ok ? "connected" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setApiStatus("offline");
      });
    return () => controller.abort();
  }, []);


  useEffect(() => {
    const input = locationFilterSearch.trim();
    const apiKey = (import.meta as any).env?.VITE_GEOAPIFY_API_KEY;
    if (input.length < 2 || !filterPanelOpen) {
      setLocationSuggestions([]);
      setLocationSuggestionsLoading(false);
      setLocationAutocompleteError(null);
      return;
    }
    if (!apiKey) {
      setLocationSuggestions([]);
      setLocationAutocompleteError("Geoapify is not configured. Add VITE_GEOAPIFY_API_KEY to your frontend .env file.");
      return;
    }
    let active = true;
    const timeout = window.setTimeout(async () => {
      try {
        setLocationSuggestionsLoading(true);
        setLocationAutocompleteError(null);
        const params = new URLSearchParams({
          text: input, format: "geojson", limit: "7", lang: "en",
          filter: "countrycode:in", apiKey,
        });
        const response = await fetch(`https://api.geoapify.com/v1/geocode/autocomplete?${params.toString()}`);
        if (!response.ok) throw new Error(`Geoapify request failed (${response.status}).`);
        const payload = await response.json();
        if (!active) return;
        const suggestions: LocationSuggestion[] = (payload.features ?? [])
          .map((feature: any) => {
            const properties = feature.properties ?? {};
            return { text: properties.formatted ?? properties.name ?? "", properties };
          })
          .filter((item: LocationSuggestion) => {
            const p = item.properties;
            const type = String(p.result_type ?? "").toLowerCase();
            const usefulTypes = ["city", "town", "village", "municipality", "state", "country"];
            return Boolean(item.text) && usefulTypes.includes(type) && Boolean(
              p.city || p.town || p.village || p.municipality || p.state || p.country || p.name
            );
          });
        setLocationSuggestions(suggestions);
      } catch (error) {
        if (active) {
          setLocationSuggestions([]);
          setLocationAutocompleteError(error instanceof Error ? error.message : "Unable to load location suggestions.");
        }
      } finally {
        if (active) setLocationSuggestionsLoading(false);
      }
    }, 300);
    return () => { active = false; window.clearTimeout(timeout); };
  }, [locationFilterSearch, filterPanelOpen]);

  function selectGeoapifyLocation(suggestion: LocationSuggestion) {
    const p = suggestion.properties;
    const resultType = String(p.result_type ?? "").toLowerCase();
    const cityValue = p.city || p.town || p.village || p.municipality || null;
    const stateValue = p.state || (resultType === "state" ? p.name : null) || null;
    const countryValue = p.country || (resultType === "country" ? p.name : null) || null;
    const selected: SelectedLocation = {
      place_id: String(p.place_id || `${cityValue ?? ""}|${stateValue ?? ""}|${countryValue ?? ""}`),
      label: String(p.formatted || suggestion.text),
      city: cityValue ? String(cityValue) : null,
      state: stateValue ? String(stateValue) : null,
      country: countryValue ? String(countryValue) : null,
    };
    if (!selected.city && !selected.state && !selected.country) {
      setLocationAutocompleteError("Choose a city, state, or country from the suggestions.");
      return;
    }
    setSelectedLocationFilters((current) => current.some((item) => item.place_id === selected.place_id) ? current : [...current, selected]);
    setLocationFilterSearch("");
    setLocationSuggestions([]);
    setLocationAutocompleteError(null);
  }

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
    setSelectedLocationFilters([]);
    setSelectedCompanyFilters([]);
    setSelectedDomainFilters([]);
    setSelectedMinExperience("");
    setSelectedMaxExperience("");
    setAppliedRoleFilters([]);
    setAppliedSkillFilters([]);
    setAppliedSeniorityFilters([]);
    setAppliedLocationFilters([]);
    setAppliedCompanyFilters([]);
    setAppliedDomainFilters([]);
    setAppliedMinExperience(null);
    setAppliedMaxExperience(null);
    setFilterPanelOpen(false);
    setRoleFilterSearch("");
    setSkillFilterSearch("");
    setLocationFilterSearch("");
    setLocationSuggestions([]);
    setCompanyFilterSearch("");
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
  const availableSeniority: SeniorityBand[] = ["Entry", "Mid", "Senior"];
  const DOMAIN_OPTIONS = [
    "TECHNICAL",
    "SALES",
    "MARKETING",
    "HR",
    "FINANCE",
    "OPERATIONS",
    "CUSTOMER_SUCCESS",
    "PRODUCT",
    "GENERAL",
  ];

  const selectedMinExperienceNumber = selectedMinExperience.trim() === "" ? null : Number(selectedMinExperience);
  const selectedMaxExperienceNumber = selectedMaxExperience.trim() === "" ? null : Number(selectedMaxExperience);
  const validMinExperience = selectedMinExperienceNumber !== null && Number.isFinite(selectedMinExperienceNumber) && selectedMinExperienceNumber >= 0
    ? selectedMinExperienceNumber : null;
  const validMaxExperience = selectedMaxExperienceNumber !== null && Number.isFinite(selectedMaxExperienceNumber) && selectedMaxExperienceNumber >= 0
    ? selectedMaxExperienceNumber : null;

  const filtersEqual = (
    left: {
      roles: string[]; skills: string[]; seniority: SeniorityBand[]; locations: SelectedLocation[];
      companies: string[]; domains: string[]; minExperience: number | null; maxExperience: number | null;
    },
    right: {
      roles: string[]; skills: string[]; seniority: SeniorityBand[]; locations: SelectedLocation[];
      companies: string[]; domains: string[]; minExperience: number | null; maxExperience: number | null;
    },
  ) =>
    JSON.stringify(left.roles) === JSON.stringify(right.roles) &&
    JSON.stringify(left.skills) === JSON.stringify(right.skills) &&
    JSON.stringify(left.seniority) === JSON.stringify(right.seniority) &&
    JSON.stringify(left.locations) === JSON.stringify(right.locations) &&
    JSON.stringify(left.companies) === JSON.stringify(right.companies) &&
    JSON.stringify(left.domains) === JSON.stringify(right.domains) &&
    left.minExperience === right.minExperience &&
    left.maxExperience === right.maxExperience;

  const hasPendingFilters = !filtersEqual(
    {
      roles: selectedRoleFilters,
      skills: selectedSkillFilters,
      seniority: selectedSeniorityFilters,
      locations: selectedLocationFilters,
      companies: selectedCompanyFilters,
      domains: selectedDomainFilters,
      minExperience: validMinExperience,
      maxExperience: validMaxExperience,
    },
    {
      roles: appliedRoleFilters,
      skills: appliedSkillFilters,
      seniority: appliedSeniorityFilters,
      locations: appliedLocationFilters,
      companies: appliedCompanyFilters,
      domains: appliedDomainFilters,
      minExperience: appliedMinExperience,
      maxExperience: appliedMaxExperience,
    },
  );

  const hasActiveFilters = Boolean(
    appliedRoleFilters.length ||
    appliedSkillFilters.length ||
    appliedSeniorityFilters.length ||
    appliedLocationFilters.length ||
    appliedCompanyFilters.length ||
    appliedDomainFilters.length ||
    appliedMinExperience !== null ||
    appliedMaxExperience !== null
  );

  const appliedFilterCount =
    appliedRoleFilters.length +
    appliedSkillFilters.length +
    appliedSeniorityFilters.length +
    appliedLocationFilters.length +
    appliedCompanyFilters.length +
    appliedDomainFilters.length +
    (appliedMinExperience !== null ? 1 : 0) +
    (appliedMaxExperience !== null ? 1 : 0);

  function openFilterPanel() {
    setSelectedRoleFilters(appliedRoleFilters);
    setSelectedSkillFilters(appliedSkillFilters);
    setSelectedSeniorityFilters(appliedSeniorityFilters);
    setSelectedLocationFilters(appliedLocationFilters);
    setSelectedCompanyFilters(appliedCompanyFilters);
    setSelectedDomainFilters(appliedDomainFilters);
    setSelectedMinExperience(appliedMinExperience === null ? "" : String(appliedMinExperience));
    setSelectedMaxExperience(appliedMaxExperience === null ? "" : String(appliedMaxExperience));
    setRoleFilterSearch("");
    setSkillFilterSearch("");
    setLocationFilterSearch("");
    setLocationSuggestions([]);
    setCompanyFilterSearch("");
    setFilterPanelOpen(true);
  }

  function closeFilterPanel(discardChanges = true) {
    if (discardChanges) {
      setSelectedRoleFilters(appliedRoleFilters);
      setSelectedSkillFilters(appliedSkillFilters);
      setSelectedSeniorityFilters(appliedSeniorityFilters);
      setSelectedLocationFilters(appliedLocationFilters);
      setSelectedCompanyFilters(appliedCompanyFilters);
      setSelectedDomainFilters(appliedDomainFilters);
      setSelectedMinExperience(appliedMinExperience === null ? "" : String(appliedMinExperience));
      setSelectedMaxExperience(appliedMaxExperience === null ? "" : String(appliedMaxExperience));
    }
    setRoleFilterSearch("");
    setSkillFilterSearch("");
    setLocationFilterSearch("");
    setLocationSuggestions([]);
    setCompanyFilterSearch("");
    setFilterPanelOpen(false);
  }

  async function handleApplyFilters(nextFilters?: {
    roles: string[];
    skills: string[];
    seniority: SeniorityBand[];
    locations: SelectedLocation[];
    companies: string[];
    domains: string[];
    minExperience: number | null;
    maxExperience: number | null;
  }) {
    if (!data?.parsed || filterLoading || loading) return;

    const roles = nextFilters?.roles ?? selectedRoleFilters;
    const skills = nextFilters?.skills ?? selectedSkillFilters;
    const seniority = nextFilters?.seniority ?? selectedSeniorityFilters;
    const locations = nextFilters?.locations ?? selectedLocationFilters;
    const companies = nextFilters?.companies ?? selectedCompanyFilters;
    const domains = nextFilters?.domains ?? selectedDomainFilters;
    // Preserve explicit null values: null means the recruiter removed that filter.
    const minExperience = nextFilters ? nextFilters.minExperience : validMinExperience;
    const maxExperience = nextFilters ? nextFilters.maxExperience : validMaxExperience;

    if (minExperience !== null && maxExperience !== null && minExperience > maxExperience) {
      setError("Minimum experience cannot be greater than maximum experience.");
      return;
    }

    setFilterLoading(true);
    setError(null);
    const startTime = performance.now();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 90000);

    try {
      const res = await fetch(FILTER_SEARCH_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          search_id: data.search_id,
          filters: {
            roles,
            skills,
            seniority,
            locations,
            companies,
            domains,
            min_experience_years: minExperience,
            max_experience_years: maxExperience,
          },
        }),
      });

      if (!res.ok) {
        throw new Error(`Filter search failed (${res.status})`);
      }

      const response: BackendSearchResponse = await res.json();
      const normalizedResults = Array.isArray(response.results)
        ? response.results
            .map(normalizeCandidate)
            .filter(
              (candidate): candidate is Candidate =>
                candidate !== null && candidate.match_status !== "NO_MATCH"
            )
        : [];

      setData({ ...response, results: normalizedResults });
      setSelectedRoleFilters(roles);
      setSelectedSkillFilters(skills);
      setSelectedSeniorityFilters(seniority);
      setSelectedLocationFilters(locations);
      setSelectedCompanyFilters(companies);
      setSelectedDomainFilters(domains);
      setSelectedMinExperience(minExperience === null ? "" : String(minExperience));
      setSelectedMaxExperience(maxExperience === null ? "" : String(maxExperience));
      setAppliedRoleFilters(roles);
      setAppliedSkillFilters(skills);
      setAppliedSeniorityFilters(seniority);
      setAppliedLocationFilters(locations);
      setAppliedCompanyFilters(companies);
      setAppliedDomainFilters(domains);
      setAppliedMinExperience(minExperience);
      setAppliedMaxExperience(maxExperience);
      setSearchTime(Number(((performance.now() - startTime) / 1000).toFixed(3)));
      setApiStatus("connected");
      setFilterPanelOpen(false);
      setRoleFilterSearch("");
      setSkillFilterSearch("");
      setLocationFilterSearch("");
        setLocationSuggestions([]);
      setCompanyFilterSearch("");
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "Filter search is taking longer than expected. Please try again shortly."
          : e instanceof Error
            ? e.message
            : "Unable to apply filters."
      );
    } finally {
      window.clearTimeout(timeoutId);
      setFilterLoading(false);
    }
  }

  type AppliedFilterKey =
    | "role"
    | "skill"
    | "location"
    | "company"
    | "domain"
    | "seniority"
    | "minExperience"
    | "maxExperience";

  function removeAppliedFilter(filter: AppliedFilterKey, value?: string) {
    const nextFilters = {
      roles: filter === "role" ? appliedRoleFilters.filter((item) => item !== value) : appliedRoleFilters,
      skills: filter === "skill" ? appliedSkillFilters.filter((item) => item !== value) : appliedSkillFilters,
      seniority: filter === "seniority" ? appliedSeniorityFilters.filter((item) => item !== value) : appliedSeniorityFilters,
      locations: filter === "location" ? appliedLocationFilters.filter((item) => item.place_id !== value) : appliedLocationFilters,
      companies: filter === "company" ? appliedCompanyFilters.filter((item) => item !== value) : appliedCompanyFilters,
      domains: filter === "domain" ? appliedDomainFilters.filter((item) => item !== value) : appliedDomainFilters,
      minExperience: filter === "minExperience" ? null : appliedMinExperience,
      maxExperience: filter === "maxExperience" ? null : appliedMaxExperience,
    };

    void handleApplyFilters(nextFilters);
  }

  function clearAllFilters() {
    void handleApplyFilters({
      roles: [],
      skills: [],
      seniority: [],
      locations: [],
      companies: [],
      domains: [],
      minExperience: null,
      maxExperience: null,
    });
  }

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

              {hasActiveFilters && (
                <div className="requirement-bar" aria-label="Applied filters">
                  <span className="criteria-heading">Filters</span>
                  {appliedRoleFilters.map((role) => (
                    <span className="requirement-pill" key={`filter-role-${role}`}>
                      {role}
                      <button type="button" aria-label={`Remove role filter ${role}`} onClick={() => removeAppliedFilter("role", role)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  {appliedSkillFilters.map((skill) => {
                    const alreadyInBaseQuery = (requirements?.skills ?? []).some((baseSkill) => baseSkill.trim().toLocaleLowerCase() === skill.trim().toLocaleLowerCase());
                    return alreadyInBaseQuery ? null : (
                      <span className="requirement-pill" key={`filter-skill-${skill}`}>
                        {skill}
                        <button type="button" aria-label={`Remove skill filter ${skill}`} onClick={() => removeAppliedFilter("skill", skill)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                      </span>
                    );
                  })}
                  {appliedLocationFilters.map((location) => (
                    <span className="requirement-pill" key={`filter-location-${location.place_id}`}>
                      {location.label} · Candidate location
                      <button type="button" aria-label={`Remove location filter ${location.label}`} onClick={() => removeAppliedFilter("location", location.place_id)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  {appliedCompanyFilters.map((company) => (
                    <span className="requirement-pill" key={`filter-company-${company}`}>
                      {company}
                      <button type="button" aria-label={`Remove company filter ${company}`} onClick={() => removeAppliedFilter("company", company)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  {appliedDomainFilters.map((domain) => (
                    <span className="requirement-pill" key={`filter-domain-${domain}`}>
                      {domain.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase())}
                      <button type="button" aria-label={`Remove domain filter ${domain}`} onClick={() => removeAppliedFilter("domain", domain)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  {appliedMinExperience !== null && (
                    <span className="requirement-pill">
                      {appliedMinExperience}+ years experience
                      <button type="button" aria-label="Remove minimum experience filter" onClick={() => removeAppliedFilter("minExperience")} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  )}
                  {appliedMaxExperience !== null && (
                    <span className="requirement-pill">
                      Up to {appliedMaxExperience} years experience
                      <button type="button" aria-label="Remove maximum experience filter" onClick={() => removeAppliedFilter("maxExperience")} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  )}
                  {appliedSeniorityFilters.map((band) => (
                    <span className="requirement-pill" key={`filter-seniority-${band}`}>
                      {band}
                      <button type="button" aria-label={`Remove seniority filter ${band}`} onClick={() => removeAppliedFilter("seniority", band)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  <button type="button" onClick={clearAllFilters} disabled={filterLoading} style={{ border: 0, background: "transparent", color: "#6d28d9", fontSize: "12px", fontWeight: 700, cursor: filterLoading ? "not-allowed" : "pointer", padding: "4px 6px" }}>
                    {filterLoading ? "Updating…" : "Clear all"}
                  </button>
                </div>
              )}

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

              <>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "16px",
                      marginBottom: "16px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                      <strong style={{ fontSize: "15px", color: "#202333" }}>
                        Matches ({resultCount})
                      </strong>
                      {hasActiveFilters && (
                        <span style={{ fontSize: "12px", color: "#777b8e" }}>
                          {appliedFilterCount} filter{appliedFilterCount === 1 ? "" : "s"} applied
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={openFilterPanel}
                      disabled={filterLoading || loading}
                      aria-haspopup="dialog"
                      aria-expanded={filterPanelOpen}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "8px",
                        border: "1px solid #d8d9e4",
                        borderRadius: "10px",
                        background: "#ffffff",
                        color: "#242638",
                        padding: "9px 14px",
                        fontSize: "13px",
                        fontWeight: 700,
                        cursor: "pointer",
                        boxShadow: "0 1px 2px rgba(24, 27, 45, 0.05)",
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M4 6h16M7 12h10M10 18h4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                      <span>Filters</span>
                      {appliedFilterCount > 0 && (
                        <span
                          style={{
                            minWidth: "20px",
                            height: "20px",
                            padding: "0 6px",
                            borderRadius: "999px",
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: "#efe8ff",
                            color: "#6d28d9",
                            fontSize: "11px",
                            fontWeight: 800,
                          }}
                        >
                          {appliedFilterCount}
                        </span>
                      )}
                    </button>
                  </div>

                  {filterPanelOpen && (
                    <div
                      role="presentation"
                      onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeFilterPanel(true);
                      }}
                      style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1000,
                        background: "rgba(20, 22, 35, 0.30)",
                        backdropFilter: "blur(2px)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "24px",
                        boxSizing: "border-box",
                      }}
                    >
                      <aside
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="filter-panel-title"
                        onMouseDown={(event) => event.stopPropagation()}
                        className="result-filter-panel"
                        style={{
                          width: "min(520px, 94vw)",
                          maxHeight: "min(720px, 88vh)",
                          background: "#ffffff",
                          border: "1px solid #e1e2ec",
                          borderRadius: "18px",
                          boxShadow: "0 24px 70px rgba(20, 22, 35, 0.22)",
                          overflow: "hidden",
                          display: "flex",
                          flexDirection: "column",
                          boxSizing: "border-box",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            justifyContent: "space-between",
                            gap: "16px",
                            padding: "22px 24px 18px",
                            borderBottom: "1px solid #ececf2",
                            background: "#ffffff",
                            flexShrink: 0,
                          }}
                        >
                          <div>
                            <h2 id="filter-panel-title" style={{ margin: 0, fontSize: "20px", fontWeight: 800, color: "#202333" }}>
                              Filters
                            </h2>
                            <p style={{ margin: "6px 0 0", fontSize: "12px", lineHeight: 1.5, color: "#777b8e" }}>
                              Select your filters, then apply them to run a refined search.
                            </p>
                          </div>
                          <button
                            type="button"
                            aria-label="Close filters"
                            onClick={() => closeFilterPanel(true)}
                            style={{
                              width: "36px",
                              height: "36px",
                              flexShrink: 0,
                              border: "1px solid #e1e2ec",
                              borderRadius: "10px",
                              background: "#f7f7fa",
                              color: "#4d5061",
                              fontSize: "21px",
                              lineHeight: 1,
                              cursor: "pointer",
                            }}
                          >
                            ×
                          </button>
                        </div>

                        <div
                          style={{
                            padding: "22px 24px 8px",
                            overflowY: "auto",
                            flex: 1,
                            minHeight: 0,
                          }}
                        >
                          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Role</legend>
                              <div className="manual-role-filter">
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={roleFilterSearch}
                                  onChange={(event) => setRoleFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      const role = roleFilterSearch.trim();
                                      if (role && !selectedRoleFilters.some((item) => item.toLocaleLowerCase() === role.toLocaleLowerCase())) {
                                        setSelectedRoleFilters((current) => [...current, role]);
                                        setRoleFilterSearch("");
                                      }
                                    }
                                    if (event.key === "Backspace" && !roleFilterSearch.trim() && selectedRoleFilters.length > 0) {
                                      setSelectedRoleFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Type a role and press Enter"
                                  aria-label="Add a role filter"
                                />
                                {selectedRoleFilters.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                    {selectedRoleFilters.map((role) => (
                                      <span key={role} style={{ display: "inline-flex", alignItems: "center", gap: "7px", minHeight: "28px", padding: "4px 7px 4px 10px", border: "1px solid #d9dbe7", borderRadius: "8px", background: "#f7f7fb", color: "#4b4e60", fontSize: "12px", fontWeight: 600, lineHeight: 1 }}>
                                        <span>{role}</span>
                                        <button type="button" aria-label={`Remove ${role}`} onClick={() => setSelectedRoleFilters((current) => current.filter((item) => item !== role))} style={{ width: "18px", height: "18px", padding: 0, border: 0, background: "transparent", color: "#5f6272", cursor: "pointer", fontSize: "15px" }}>×</button>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Skills</legend>
                              <div className="manual-skill-filter">
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={skillFilterSearch}
                                  onChange={(event) => setSkillFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      const skill = skillFilterSearch.trim();
                                      if (skill && !selectedSkillFilters.some((item) => item.toLocaleLowerCase() === skill.toLocaleLowerCase())) {
                                        setSelectedSkillFilters((current) => [...current, skill]);
                                        setSkillFilterSearch("");
                                      }
                                    }
                                    if (event.key === "Backspace" && !skillFilterSearch.trim() && selectedSkillFilters.length > 0) {
                                      setSelectedSkillFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Type a skill and press Enter"
                                  aria-label="Add a skill filter"
                                />
                                {selectedSkillFilters.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                    {selectedSkillFilters.map((skill) => (
                                      <span key={skill} style={{ display: "inline-flex", alignItems: "center", gap: "7px", minHeight: "28px", padding: "4px 7px 4px 10px", border: "1px solid #d9dbe7", borderRadius: "8px", background: "#f7f7fb", color: "#4b4e60", fontSize: "12px", fontWeight: 600, lineHeight: 1 }}>
                                        <span>{skill}</span>
                                        <button type="button" aria-label={`Remove ${skill}`} onClick={() => setSelectedSkillFilters((current) => current.filter((item) => item !== skill))} style={{ width: "18px", height: "18px", padding: 0, border: 0, background: "transparent", color: "#5f6272", cursor: "pointer", fontSize: "15px" }}>×</button>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Location</legend>
                              <div style={{ position: "relative" }}>
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={locationFilterSearch}
                                  onChange={(event) => setLocationFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter" && locationSuggestions.length > 0) {
                                      event.preventDefault();
                                      selectGeoapifyLocation(locationSuggestions[0]);
                                    }
                                    if (event.key === "Escape") setLocationSuggestions([]);
                                    if (event.key === "Backspace" && !locationFilterSearch.trim() && selectedLocationFilters.length > 0) {
                                      setSelectedLocationFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Search city or locality"
                                  aria-label="Search for a candidate location"
                                  autoComplete="off"
                                />
                                {(locationSuggestionsLoading || locationSuggestions.length > 0 || locationAutocompleteError) && (
                                  <div
                                    role="listbox"
                                    style={{
                                      position: "absolute",
                                      zIndex: 30,
                                      top: "calc(100% + 5px)",
                                      left: 0,
                                      right: 0,
                                      background: "#fff",
                                      border: "1px solid #d9dce8",
                                      borderRadius: "9px",
                                      boxShadow: "0 8px 24px rgba(20, 25, 45, 0.12)",
                                      maxHeight: "220px",
                                      overflowY: "auto",
                                    }}
                                  >
                                    {locationSuggestionsLoading && (
                                      <div style={{ padding: "11px 13px", color: "#73788b", fontSize: "13px" }}>Searching locations…</div>
                                    )}
                                    {locationAutocompleteError && (
                                      <div style={{ padding: "11px 13px", color: "#b42318", fontSize: "12px" }}>{locationAutocompleteError}</div>
                                    )}
                                    {locationSuggestions.map((suggestion, index) => (
                                      <button
                                        type="button"
                                        role="option"
                                        aria-selected="false"
                                        key={`${suggestion.properties?.place_id ?? suggestion.text}-${index}`}
                                        onMouseDown={(event) => event.preventDefault()}
                                        onClick={() => selectGeoapifyLocation(suggestion)}
                                        style={{
                                          display: "block",
                                          width: "100%",
                                          padding: "11px 13px",
                                          border: 0,
                                          borderBottom: "1px solid #f0f1f5",
                                          background: "#fff",
                                          color: "#25283a",
                                          textAlign: "left",
                                          cursor: "pointer",
                                          fontSize: "13px",
                                        }}
                                      >
                                        <span style={{ display: "flex", alignItems: "center", gap: "9px" }}>
                                          <span aria-hidden="true">⌖</span>
                                          <span>{suggestion.text}</span>
                                        </span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                             
                              {selectedLocationFilters.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                  {selectedLocationFilters.map((location) => (
                                    <span className="requirement-pill" key={location.place_id}>
                                      {location.label}
                                      <button type="button" aria-label={`Remove ${location.label}`} onClick={() => setSelectedLocationFilters((current) => current.filter((item) => item.place_id !== location.place_id))} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: "pointer" }}>×</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Experience</legend>
                              <p className="filter-group-note">Filter by total professional experience.</p>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                                <input className="filter-dropdown-search" type="number" min="0" step="0.5" value={selectedMinExperience} onChange={(event) => setSelectedMinExperience(event.target.value)} placeholder="Min years" aria-label="Minimum experience in years" />
                                <input className="filter-dropdown-search" type="number" min="0" step="0.5" value={selectedMaxExperience} onChange={(event) => setSelectedMaxExperience(event.target.value)} placeholder="Max years" aria-label="Maximum experience in years" />
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Seniority</legend>
                              <p className="filter-group-note">Based on total experience</p>
                              {availableSeniority.map((band) => (
                                <label className="filter-option" key={band}>
                                  <input
                                    type="checkbox"
                                    checked={selectedSeniorityFilters.includes(band)}
                                    onChange={() => setSelectedSeniorityFilters((current) => current.includes(band) ? current.filter((item) => item !== band) : [...current, band])}
                                  />
                                  <span>{band}{band === "Entry" ? " · 0–2 years" : band === "Mid" ? " · 3–7 years" : " · 8+ years"}</span>
                                </label>
                              ))}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Company</legend>
                              <input
                                className="filter-dropdown-search"
                                type="text"
                                value={companyFilterSearch}
                                onChange={(event) => setCompanyFilterSearch(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    const company = companyFilterSearch.trim();
                                    if (company && !selectedCompanyFilters.some((item) => item.toLocaleLowerCase() === company.toLocaleLowerCase())) {
                                      setSelectedCompanyFilters((current) => [...current, company]);
                                      setCompanyFilterSearch("");
                                    }
                                  }
                                  if (event.key === "Backspace" && !companyFilterSearch.trim() && selectedCompanyFilters.length > 0) {
                                    setSelectedCompanyFilters((current) => current.slice(0, -1));
                                  }
                                }}
                                placeholder="Type a company and press Enter"
                                aria-label="Add a company filter"
                              />
                              {selectedCompanyFilters.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                  {selectedCompanyFilters.map((company) => (
                                    <span className="requirement-pill" key={company}>
                                      {company}
                                      <button type="button" aria-label={`Remove ${company}`} onClick={() => setSelectedCompanyFilters((current) => current.filter((item) => item !== company))} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: "pointer" }}>×</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Domain</legend>
                              {DOMAIN_OPTIONS.map((domain) => (
                                <label className="filter-option" key={domain}>
                                  <input type="checkbox" checked={selectedDomainFilters.includes(domain)} onChange={() => setSelectedDomainFilters((current) => current.includes(domain) ? current.filter((item) => item !== domain) : [...current, domain])} />
                                  <span>{domain.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase())}</span>
                                </label>
                              ))}
                            </fieldset>
                          </div>
                        </div>

                        <div
                          style={{
                            padding: "14px 24px 18px",
                            background: "#ffffff",
                            borderTop: "1px solid #ececf2",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "12px",
                            flexShrink: 0,
                          }}
                        >
                          <button
                            type="button"
                            onClick={clearAllFilters}
                            disabled={(!hasActiveFilters && !hasPendingFilters) || filterLoading}
                            style={{
                              border: 0,
                              background: "transparent",
                              color: "#6d28d9",
                              fontSize: "13px",
                              fontWeight: 700,
                              cursor: "pointer",
                              padding: "10px 2px",
                              opacity: (!hasActiveFilters && !hasPendingFilters) || filterLoading ? 0.45 : 1,
                            }}
                          >
                            Clear all
                          </button>

                          <div style={{ display: "flex", gap: "8px" }}>
                            <button
                              type="button"
                              onClick={() => closeFilterPanel(true)}
                              disabled={filterLoading}
                              style={{
                                border: "1px solid #d8d9e4",
                                borderRadius: "9px",
                                background: "#fff",
                                color: "#36394a",
                                padding: "10px 15px",
                                fontSize: "13px",
                                fontWeight: 700,
                                cursor: "pointer",
                              }}
                            >
                              Cancel
                            </button>

                            <button
                              type="button"
                              className="filter-apply-button"
                              disabled={!hasPendingFilters || filterLoading}
                              onClick={() => void handleApplyFilters()}
                              style={{
                                border: "1px solid #171a2b",
                                borderRadius: "9px",
                                background: !hasPendingFilters || filterLoading ? "#e9e9ee" : "#171a2b",
                                color: !hasPendingFilters || filterLoading ? "#9295a4" : "#ffffff",
                                padding: "10px 16px",
                                fontSize: "13px",
                                fontWeight: 800,
                                cursor: !hasPendingFilters || filterLoading ? "not-allowed" : "pointer",
                                boxShadow: !hasPendingFilters || filterLoading ? "none" : "0 4px 12px rgba(23, 26, 43, 0.12)",
                              }}
                            >
                              {filterLoading ? "Applying…" : "Apply filters"}
                            </button>
                          </div>
                        </div>
                      </aside>
                    </div>
                  )}

                  <div className="results-list-column">
                    {resultCount ? (
                      <div className="candidate-list">
                  {(data?.results ?? []).map(
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

                              {candidate.matched_experience && (
                                <div className="candidate-email">
                                  <strong>Matched experience:</strong>{" "}
                                  {candidate.matched_experience.role || "Relevant experience"}
                                  {candidate.matched_experience.company &&
                                    ` · ${candidate.matched_experience.company}`}
                                  {(candidate.matched_experience.start_date ||
                                    candidate.matched_experience.end_date ||
                                    candidate.matched_experience.is_current) && (
                                    <>
                                      {" · "}
                                      {formatTimelineDate(candidate.matched_experience.start_date)}
                                      {" – "}
                                      {candidate.matched_experience.is_current
                                        ? "Present"
                                        : formatTimelineDate(candidate.matched_experience.end_date)}
                                    </>
                                  )}
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
                        <strong>No candidates found</strong>
                        <p>Try changing the search or adjusting the applied filters.</p>
                      </div>
                    )}
                  </div>
              </>
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
              <div className="profile-tab-panel" data-tab="overview" hidden={profileTab !== "overview"}>
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
              </div>

              <div className="profile-tab-panel" data-tab="experience" hidden={profileTab !== "experience"}>
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
              </div>

              <div className="profile-tab-panel" data-tab="projects" hidden={profileTab !== "projects"}>
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
              </div>

              <div className="profile-tab-panel" data-tab="education" hidden={profileTab !== "education"}>
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
              </div>

              <div className="profile-tab-panel" data-tab="skills" hidden={profileTab !== "skills"}>
                <section className="profile-section">
                  <h3>Skills</h3>
                  {selectedProfile.profile_skills.length ? <div className="profile-skill-list">{selectedProfile.profile_skills.map((skill) => <span key={skill}>{skill}</span>)}</div> : <p className="profile-muted">No skills available.</p>}
                </section>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
