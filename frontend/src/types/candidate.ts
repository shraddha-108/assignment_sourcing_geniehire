import type { SeniorityFilterBand } from "../features/filters/filterExperience";

export type MatchedSkill = {
  skill: string;
  last_used?: string | null;
  total_months?: number;
};

export type ExperienceTimelineEntry = {
  role?: string | null;
  company?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  duration_months?: number | null;
  description?: string | null;
};

export type MatchedExperience = {
  role?: string | null;
  company?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  duration_months?: number | null;
  description?: string | null;
};

export type ProjectEntry = {
  title: string;
  description?: string | null;
  url?: string | null;
  skills?: string[];
};

export type EducationEntry = {
  institution?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  start_date?: string | null;
  end_date?: string | null;
};

export type BackendMatchedSkill =
  | string
  | {
      skill?: string;
      last_used?: string | null;
      last_used_date?: string | null;
      total_months?: number;
    };

export type Evidence = {
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

export type MatchedRequirement = {
  type: string;
  requirement_types?: string[];
  requirement: string;
  matched: boolean;
  mandatory?: boolean;
  match_mode?: "HARD" | "SOFT";
  status?: "MATCH" | "PARTIAL_MATCH" | "NO_MATCH";
  candidate_value?: string | number | null;
  experience_scope?: "OVERALL" | "RELEVANT_ROLE";
  experience_months?: number | null;
  seniority_fit?: "PREFERRED" | "ACCEPTABLE" | "OUTSIDE";
  partial_reason?: string;
  evidence?: Evidence[];
};

export type BackendExplanation = string;

export type BackendCandidate = {
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

export type Candidate = {
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
  shortlistSourceQueries?: string[];
};

export type ContactCandidate = Pick<
  Candidate,
  "id" | "name" | "email" | "phone" | "linkedin_url" | "headline" | "location"
>;

export type StructuredRequirements = {
  skills: string[];
  roles?: string[];
  companies?: string[];
  domains?: string[];
  location?: string | null;
  role?: string | null;
  recency_months: number | null;
  experience_min_years: number | null;
  experience_max_years?: number | null;
  relevant_experience_min_years?: number | null;
  experience_scope?: string | null;
  seniority_filter?: {
    seniority: string;
    preferred_min_months: number;
    preferred_max_months: number | null;
    acceptable_min_months: number;
    acceptable_max_months: number | null;
    experience_scope: "OVERALL" | "RELEVANT_ROLE";
    role_titles?: string[];
  } | null;
};

export type RoutingPacket = {
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

export type SearchResponse = {
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

export type BackendSearchResponse = Omit<SearchResponse, "results"> & {
  results: BackendCandidate[];
};

export type SelectedLocation = {
  place_id: string;
  label: string;
  city: string | null;
  state: string | null;
  country: string | null;
};

export type LocationSuggestion = {
  text: string;
  properties: any;
};

export type SeniorityBand = SeniorityFilterBand;

export type CandidateView = "results" | "shortlist" | "contacts" | "hidden" | "compare" | "outreach";

