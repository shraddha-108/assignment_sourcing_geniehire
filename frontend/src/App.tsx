import { useEffect, useLayoutEffect, useRef, useState } from "react";
import "./App.css";
import { SearchHeader } from "./components/SearchHeader";
import { FilterDialog } from "./components/FilterDialog";
import { CandidateWorkspace } from "./components/CandidateWorkspace";
import { SearchHero } from "./components/SearchHero";
import { SearchResultSummary } from "./components/SearchResultSummary";
import { CandidateProfileDialog, type ProfileTab } from "./components/CandidateProfileDialog";
import {
  BANDS,
} from "./features/filters/filterExperience";
import {
  loadContacts,
  saveContacts,
  type ContactRecord,
  type ContactStatus,
} from "./features/contacts/contactTracker";
import {
  hasAnyFilter,
  loadSearch,
  saveSearch,
  type SavedFilters,
} from "./features/search/searchSession";
import type {
  BackendCandidate,
  BackendSearchResponse,
  Candidate,
  CandidateView,
  ContactCandidate,
  Evidence,
  ExperienceTimelineEntry,
  LocationSuggestion,
  MatchedRequirement,
  MatchedSkill,
  SearchResponse,
  SelectedLocation,
  SeniorityBand,
} from "./types/candidate";
import { getMatchedExperience } from "./features/candidates/candidatePresentation";

const API_URL = "http://127.0.0.1:8000/search";
const SPELLING_CHECK_URL = "http://127.0.0.1:8000/search/suggestion";
const FILTER_SEARCH_URL = "http://127.0.0.1:8000/search/refine";
const RESUME_API_URL = "http://127.0.0.1:8000/candidates";

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
  const [apiStatus, setApiStatus] = useState<"checking" | "connected" | "offline">("checking");
  const [searchTime, setSearchTime] =
    useState<number | null>(null);
  const [error, setError] =
    useState<string | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<Candidate | null>(null);
  const [candidateView, setCandidateView] = useState<CandidateView>("results");
  const candidateTabScrollRef = useRef<HTMLDivElement | null>(null);
  const candidateTabScrollPositionsRef = useRef<Partial<Record<CandidateView, number>>>({});
  const [shortlistedCandidates, setShortlistedCandidates] = useState<Candidate[]>([]);
  const [hiddenCandidates, setHiddenCandidates] = useState<Candidate[]>([]);
  const [contacts, setContacts] = useState<ContactRecord<ContactCandidate>[]>([]);
  const [contactsReady, setContactsReady] = useState(false);
  const [contactsStorageError, setContactsStorageError] = useState<string | null>(null);
  const [compareCandidateIds, setCompareCandidateIds] = useState<number[]>([]);
  const [outreachCandidateIds, setOutreachCandidateIds] = useState<number[]>([]);
  const [outreachSubject, setOutreachSubject] = useState("A role that may fit your experience");
  const [outreachMessage, setOutreachMessage] = useState(
    "Hi {{firstName}},\n\nI came across your profile and was impressed by your experience. We’re speaking with candidates for a role related to {{searchQuery}} and I thought it could be a good fit.\n\nWould you be open to a short conversation this week?\n\nBest,\n[Your name]"
  );
  const [profileTab, setProfileTab] = useState<ProfileTab>("overview");
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
  const restoredRef = useRef(false);
  const pendingFiltersRef = useRef<SavedFilters | null>(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [roleFilterSearch, setRoleFilterSearch] = useState("");
  const [skillFilterSearch, setSkillFilterSearch] = useState("");
  const [locationFilterSearch, setLocationFilterSearch] = useState("");
  const [locationSuggestions, setLocationSuggestions] = useState<LocationSuggestion[]>([]);
  const [locationSuggestionsLoading, setLocationSuggestionsLoading] = useState(false);
  const [locationAutocompleteError, setLocationAutocompleteError] = useState<string | null>(null);
  const [companyFilterSearch, setCompanyFilterSearch] = useState("");

  function navigateCandidateView(nextView: CandidateView, resetNext = false) {
    const scrollPanel = candidateTabScrollRef.current;
    if (scrollPanel) {
      candidateTabScrollPositionsRef.current[candidateView] = scrollPanel.scrollTop;
    }
    if (resetNext) delete candidateTabScrollPositionsRef.current[nextView];
    setCandidateView(nextView);
  }

  function contactCandidateSnapshot(candidate: ContactCandidate): ContactCandidate {
    return {
      id: candidate.id,
      name: candidate.name,
      email: candidate.email,
      phone: candidate.phone,
      linkedin_url: candidate.linkedin_url,
      headline: candidate.headline,
      location: candidate.location,
    };
  }

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

  function toggleShortlist(candidate: Candidate) {
    const isShortlisted = shortlistedCandidates.some((item) => item.id === candidate.id);
    setShortlistedCandidates((current) =>
      isShortlisted
        ? current.filter((item) => item.id !== candidate.id)
        : [
            ...current,
            {
              ...candidate,
              shortlistSourceQueries: [
                data?.parsed.original_query?.trim() || query.trim(),
              ].filter(Boolean),
            },
          ]
    );
    if (isShortlisted) {
      setCompareCandidateIds((current) => current.filter((id) => id !== candidate.id));
    }
  }

  function hideCandidate(candidate: Candidate) {
    setHiddenCandidates((current) =>
      current.some((item) => item.id === candidate.id)
        ? current
        : [...current, candidate]
    );
  }

  function continueToOutreach() {
    if (compareCandidates.length < 2) return;
    setOutreachCandidateIds(compareCandidates.map((candidate) => candidate.id));
    const now = new Date().toISOString();
    const nextContacts = [...contacts];
    for (const candidate of compareCandidates) {
      const existingIndex = nextContacts.findIndex((contact) => contact.candidate.id === candidate.id);
      if (existingIndex >= 0) {
        nextContacts[existingIndex] = {
          ...nextContacts[existingIndex],
          candidate: contactCandidateSnapshot(candidate),
        };
      } else {
        nextContacts.push({
          candidate: contactCandidateSnapshot(candidate),
          status: "To contact",
          addedAt: now,
          updatedAt: now,
          contactedAt: null,
          sourceQuery: data?.parsed.original_query?.trim() || query.trim() || null,
        });
      }
    }
    setContacts(nextContacts);
    const saved = saveContacts(nextContacts);
    setContactsStorageError(saved.error);
    navigateCandidateView("outreach");
  }

  function updateContactStatus(candidateId: number, status: ContactStatus) {
    const now = new Date().toISOString();
    const existing = contacts.find((contact) => contact.candidate.id === candidateId);
    const contactedAt = status === "To contact"
      ? null
      : existing?.contactedAt ?? now;
    const candidate = shortlistedCandidates.find((item) => item.id === candidateId) ??
      data?.results.find((item) => item.id === candidateId) ??
      existing?.candidate;
    if (!candidate) return;
    const nextContact: ContactRecord<ContactCandidate> = existing
      ? {
          ...existing,
          candidate: contactCandidateSnapshot(candidate),
          status,
          updatedAt: now,
          contactedAt,
        }
      : {
          candidate: contactCandidateSnapshot(candidate),
          status,
          addedAt: now,
          updatedAt: now,
          contactedAt,
          sourceQuery: data?.parsed.original_query?.trim() || query.trim() || null,
        };
    const nextContacts = existing
      ? contacts.map((contact) => contact.candidate.id === candidateId ? nextContact : contact)
      : [...contacts, nextContact];
    setContacts(nextContacts);
    const saved = saveContacts(nextContacts);
    setContactsStorageError(saved.error);
  }

  function removeContact(candidateId: number) {
    const nextContacts = contacts.filter((contact) => contact.candidate.id !== candidateId);
    setContacts(nextContacts);
    const saved = saveContacts(nextContacts);
    setContactsStorageError(saved.error);
  }

  useEffect(() => {
    const loaded = loadContacts<ContactCandidate>();
    if (loaded.value) setContacts(loaded.value);
    setContactsStorageError(loaded.error);
    setContactsReady(loaded.value !== null);
  }, []);

  useEffect(() => {
    if (!contactsReady) return;
    const saved = saveContacts(contacts);
    setContactsStorageError(saved.error);
  }, [contacts, contactsReady]);

  function restoreCandidate(candidateId: number) {
    setHiddenCandidates((current) => current.filter((item) => item.id !== candidateId));
  }

  function toggleCompare(candidateId: number) {
    setCompareCandidateIds((current) =>
      current.includes(candidateId)
        ? current.filter((id) => id !== candidateId)
        : current.length < 4
          ? [...current, candidateId]
          : current
    );
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

  useLayoutEffect(() => {
    const scrollPanel = candidateTabScrollRef.current;
    if (scrollPanel) {
      scrollPanel.scrollTop = candidateTabScrollPositionsRef.current[candidateView] ?? 0;
    }
  }, [candidateView]);

  useEffect(() => {
    const originalQuery = data?.parsed?.original_query;
    if (!originalQuery || pendingFiltersRef.current !== null) return;
    saveSearch({
      query: originalQuery,
      filters: {
        roles: appliedRoleFilters,
        skills: appliedSkillFilters,
        seniority: appliedSeniorityFilters,
        locations: appliedLocationFilters,
        companies: appliedCompanyFilters,
        domains: appliedDomainFilters,
        minExperience: appliedMinExperience,
        maxExperience: appliedMaxExperience,
      },
    });
  }, [
    data,
    appliedRoleFilters,
    appliedSkillFilters,
    appliedSeniorityFilters,
    appliedLocationFilters,
    appliedCompanyFilters,
    appliedDomainFilters,
    appliedMinExperience,
    appliedMaxExperience,
  ]);

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const saved = loadSearch();
    if (!saved) return;
    setQuery(saved.query);
    if (hasAnyFilter(saved.filters)) pendingFiltersRef.current = saved.filters;
    void handleSearch(saved.query, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (pendingFiltersRef.current === null) return;
    if (error) {
      pendingFiltersRef.current = null;
      return;
    }
    if (!data?.parsed || loading || filterLoading) return;

    const pending = pendingFiltersRef.current;
    pendingFiltersRef.current = null;
    void handleApplyFilters({
      ...pending,
      seniority: pending.seniority as SeniorityBand[],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, loading, filterLoading, error]);


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
    navigateCandidateView("results", true);
    setCompareCandidateIds([]);
    setOutreachCandidateIds([]);
    setHiddenCandidates([]);
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

      const currentQuery = response.parsed?.original_query?.trim() || searchText.trim();
      setShortlistedCandidates((current) =>
        current.map((shortlisted) => {
          const updatedCandidate = normalizedResults.find(
            (candidate) => candidate.id === shortlisted.id
          );
          if (!updatedCandidate) return shortlisted;
          return {
            ...updatedCandidate,
            shortlistSourceQueries: [
              ...new Set([
                ...(shortlisted.shortlistSourceQueries ?? []),
                currentQuery,
              ].filter(Boolean)),
            ],
          };
        })
      );
      setContacts((current) =>
        current.map((contact) => {
          const updatedCandidate = normalizedResults.find(
            (candidate) => candidate.id === contact.candidate.id
          );
          return updatedCandidate
            ? { ...contact, candidate: contactCandidateSnapshot(updatedCandidate) }
            : contact;
        })
      );

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
  const seniorityPolicy = requirements?.seniority_filter ?? null;
  const queryFilterChips = [
    ...(requirements?.skills ?? []).map((value) => ({ key: `skill:${value}`, label: `Skill: ${value}` })),
    ...[...(requirements?.roles ?? []), ...(requirements?.role ? [requirements.role] : [])].map((value) => ({ key: `role:${value}`, label: `Role: ${value}` })),
    ...(requirements?.companies ?? []).map((value) => ({ key: `company:${value}`, label: `Company: ${value}` })),
    ...(requirements?.domains ?? []).map((value) => ({ key: `domain:${value}`, label: `Domain: ${value.replaceAll("_", " ")}` })),
    ...(requirements?.location ? [{ key: "location", label: `Location: ${requirements.location}` }] : []),
    ...(requirements?.experience_min_years != null || requirements?.experience_max_years != null
      ? [{
          key: "experience",
          label: `Experience: ${requirements.experience_min_years != null && requirements.experience_max_years != null
            ? `${requirements.experience_min_years}–${requirements.experience_max_years} years`
            : requirements.experience_min_years != null
              ? `${requirements.experience_min_years}+ years`
              : `up to ${requirements.experience_max_years} years`}`,
        }]
      : []),
    ...(seniorityPolicy
      ? [{
          key: "seniority",
          label: `${seniorityPolicy.seniority} seniority (${seniorityPolicy.experience_scope === "RELEVANT_ROLE" ? "relevant role" : "overall"} experience)`,
        }]
      : []),
  ].filter((item, index, items) => items.findIndex((candidate) => candidate.key.toLocaleLowerCase() === item.key.toLocaleLowerCase()) === index);
  const queryFilterValues = {
    roles: [...(requirements?.roles ?? []), ...(requirements?.role ? [requirements.role] : [])],
    skills: requirements?.skills ?? [],
    companies: requirements?.companies ?? [],
    domains: requirements?.domains ?? [],
  };
  const queryAlreadyIncludes = (field: keyof typeof queryFilterValues, value: string) => {
    const normalize = (item: string) => item.trim().toLocaleLowerCase().replaceAll("_", " ");
    return queryFilterValues[field].some((item) => normalize(item) === normalize(value));
  };
  const queryAlreadyIncludesLocation = (location: SelectedLocation) => {
    const normalize = (value: string) => value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
    const queryLocation = requirements?.location ? normalize(requirements.location) : "";
    return Boolean(queryLocation && [
      location.city,
      location.state,
      location.country,
      location.label,
    ].some((value) => {
      if (!value) return false;
      const candidate = normalize(value);
      return candidate === queryLocation || candidate.startsWith(`${queryLocation},`) || queryLocation.startsWith(`${candidate},`);
    }));
  };
  const queryAlreadyIncludesLocationText = (value: string) =>
    Boolean(requirements?.location && requirements.location.trim().toLocaleLowerCase() === value.trim().toLocaleLowerCase());
  const queryAlreadyIncludesLocationSuggestion = (suggestion: LocationSuggestion) => {
    const p = suggestion.properties;
    const city = p.city || p.town || p.village || p.municipality || null;
    const state = p.state || null;
    const country = p.country || null;
    return queryAlreadyIncludesLocation({
      place_id: String(p.place_id || ""),
      label: String(p.formatted || suggestion.text),
      city: city ? String(city) : null,
      state: state ? String(state) : null,
      country: country ? String(country) : null,
    });
  };
  const formatSeniorityRange = (minMonths: number, maxMonths: number | null) => {
    const formatYears = (months: number) => {
      const years = months / 12;
      return Number.isInteger(years) ? String(years) : years.toFixed(1).replace(/\.0$/, "");
    };
    return maxMonths == null
      ? `${formatYears(minMonths)}+ years`
      : `${formatYears(minMonths)}–${formatYears(maxMonths)} years`;
  };
  const visibleAssumptions = (data?.parsed.assumptions ?? []).filter((assumption) => {
    const isObsoleteSeniorityWarning = /seniority wording.*not converted to an experience-years filter/i.test(assumption);
    return !(seniorityPolicy && isObsoleteSeniorityWarning);
  });
  const resultCount =
    data?.results.length ?? 0;
  const hiddenCandidateIds = new Set(hiddenCandidates.map((candidate) => candidate.id));
  const visibleResultCandidates = (data?.results ?? []).filter(
    (candidate) => !hiddenCandidateIds.has(candidate.id)
  );
  const activeCandidates =
    candidateView === "shortlist"
      ? shortlistedCandidates
      : candidateView === "hidden"
        ? hiddenCandidates
        : visibleResultCandidates;
  const compareCandidates = shortlistedCandidates.filter((candidate) =>
    compareCandidateIds.includes(candidate.id)
  );
  const outreachCandidates = shortlistedCandidates.filter((candidate) =>
    outreachCandidateIds.includes(candidate.id)
  );
  const includedDomainCount = new Set([...selectedDomainFilters, ...queryFilterValues.domains]).size;

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

    if (minExperience !== null && maxExperience !== null && minExperience >= maxExperience + 1) {
      setError("Minimum experience must be less than the end of the maximum year.");
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
            experience_min: minExperience,
            experience_max: maxExperience,
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

  return (
    <div className={`app-shell${data && !loading ? " has-search-results" : ""}`}>
      <SearchHeader status={apiStatus} />

      <main className="main-content">
        <SearchHero query={query} loading={loading} suggestedQuery={suggestedQuery} onQueryChange={setQuery} onClearSuggestion={() => setSuggestedQuery(null)} onSubmit={() => void handleSearch()} onSearchSuggestion={(value) => { setQuery(value); void handleSearch(value, true); }} onSearchOriginal={() => void handleSearch(query, true)} />

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
              <strong>Searching for candidates</strong>

              <p>
                Finding profiles that match your requirements. This may take a moment.
              </p>
            </div>
          </section>
        )}

        {data &&
          !loading && (
            <section className="results-section">
              <SearchResultSummary
                data={data}
                resultCount={resultCount}
                searchTime={searchTime}
                requirements={requirements}
                semanticCriteria={semanticCriteria}
                temporalCriteria={temporalCriteria}
                seniorityPolicy={seniorityPolicy}
                formatSeniorityRange={formatSeniorityRange}
              />

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
                      {BANDS.find((item) => item.key === band)?.label ?? band}
                      <button type="button" aria-label={`Remove seniority filter ${band}`} onClick={() => removeAppliedFilter("seniority", band)} disabled={filterLoading} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: filterLoading ? "not-allowed" : "pointer" }}>×</button>
                    </span>
                  ))}
                  <button type="button" onClick={clearAllFilters} disabled={filterLoading} style={{ border: 0, background: "transparent", color: "#6d28d9", fontSize: "12px", fontWeight: 700, cursor: filterLoading ? "not-allowed" : "pointer", padding: "4px 6px" }}>
                    {filterLoading ? "Updating…" : "Clear all"}
                  </button>
                </div>
              )}

              {visibleAssumptions.length > 0 && (
                <div className="assumption-info">
                  <strong>Search assumptions</strong>
                  {visibleAssumptions.map((assumption) => (
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

                  <FilterDialog
                    state={{
                      open: filterPanelOpen, loading: filterLoading, hasActiveFilters, hasPendingFilters, queryFilterChips, includedDomainCount,
                      roleFilterSearch, selectedRoleFilters, skillFilterSearch, selectedSkillFilters, selectedSeniorityFilters,
                      locationFilterSearch, locationSuggestions, locationSuggestionsLoading, locationAutocompleteError, selectedLocationFilters,
                      selectedMinExperience, selectedMaxExperience, companyFilterSearch, selectedCompanyFilters, selectedDomainFilters,
                    }}
                    actions={{
                      setters: {
                        setRoleFilterSearch, setSelectedRoleFilters, setSkillFilterSearch, setSelectedSkillFilters, setSelectedSeniorityFilters,
                        setLocationFilterSearch, setLocationSuggestions, setSelectedLocationFilters, setSelectedMinExperience, setSelectedMaxExperience,
                        setCompanyFilterSearch, setSelectedCompanyFilters, setSelectedDomainFilters,
                      },
                      closeFilterPanel, clearAllFilters, applyFilters: handleApplyFilters, selectGeoapifyLocation, queryAlreadyIncludes,
                      queryAlreadyIncludesLocationText, queryAlreadyIncludesLocationSuggestion,
                    }}
                  />

                  <CandidateWorkspace
                    state={{ candidateView, shortlistedCandidates, hiddenCandidates, contacts, contactsStorageError, compareCandidateIds, outreachCandidateIds, outreachSubject, outreachMessage }}
                    data={{ visibleResultCandidates, activeCandidates, compareCandidates, outreachCandidates, requirements, seniorityPolicy, searchQuery: data?.parsed.original_query ?? "" }}
                    actions={{ navigateCandidateView, openProfile, updateContactStatus, removeContact, setOutreachCandidateIds, continueToOutreach, setOutreachSubject, setOutreachMessage, toggleCompare, hideCandidate, restoreCandidate, toggleShortlist }}
                    tabScrollRef={candidateTabScrollRef}
                    tabScrollPositionsRef={candidateTabScrollPositionsRef}
                  />
              </>
            </section>
          )}
      </main>

      <CandidateProfileDialog candidate={selectedProfile} profileTab={profileTab} onProfileTabChange={setProfileTab} onClose={() => setSelectedProfile(null)} onViewResume={(candidateId) => void handleViewResume(candidateId)} />
    </div>
  );
}

export default App;
