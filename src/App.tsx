import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/search";
const RESUME_API_URL = "http://127.0.0.1:8000/candidates";

type MatchedSkill = {
  skill: string;
  last_used: string;
  total_months: number;
};

type StructuredCandidate = {
  id: number;
  name: string;
  email: string | null;
  score: number;
  matched_skills: MatchedSkill[];
};

type Evidence = {
  source: string;
  text: string;
  similarity: number;
};

type SemanticCandidate = {
  id: number;
  name: string;
  email: string | null;
  score: number;
  match_score: number;
  evidence: Evidence[];
};

type StructuredRequirements = {
  skills: string[];
  role?: string | null;
  recency_months: number | null;
  experience_min_years: number | null;
  experience_scope?: string | null;
};

type RoutingPacket = {
  original_query: string;
  requested_count: number;
  count_explicit: boolean;
  structured_requirements: StructuredRequirements;
  semantic_requirement: string | null;
  exclusions: unknown[];
};

type SearchResponse = {
  route: string;
  parsed: RoutingPacket;
  results: StructuredCandidate[] | SemanticCandidate[];
  message?: string;
  valid?: boolean;
  errors?: string[];
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

function formatDate(dateString: string): string {
  if (!dateString) {
    return "Unknown";
  }

  const date = new Date(dateString);

  if (Number.isNaN(date.getTime())) {
    return dateString;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatMonths(months: number): string {
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

function App() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchTime, setSearchTime] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query.trim() || loading) {
      return;
    }

    setData(null);
    setError(null);
    setSearchTime(null);
    setLoading(true);

    const startTime = performance.now();

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: query.trim(),
        }),
      });

      if (!res.ok) {
        throw new Error(`Server error (${res.status})`);
      }

      const response: SearchResponse = await res.json();

      const endTime = performance.now();

      setSearchTime(
        Number(((endTime - startTime) / 1000).toFixed(3))
      );

      if (response.valid === false) {
        setError(
          response.errors?.join(", ") || "Invalid query"
        );
        setData(null);
        return;
      }

      setData(response);
    } catch (e) {
      const endTime = performance.now();

      setSearchTime(
        Number(((endTime - startTime) / 1000).toFixed(3))
      );

      setError(
        e instanceof Error
          ? e.message
          : "Something went wrong. Is the backend running?"
      );

      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleViewResume(candidateId: number) {
    try {
      const response = await fetch(
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
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to open resume"
      );
    }
  }

  const requirements =
    data?.parsed?.structured_requirements;

  const isStructured =
    data?.route === "STRUCTURED";

  const isSemantic =
    data?.route === "SEMANTIC";

  const isHybrid =
    data?.route === "HYBRID";

  const resultCount = data?.results.length ?? 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">G</div>

          <div>
            <div className="brand-name">GenieHire</div>
            <div className="brand-subtitle">
              Recruiter Intelligence
            </div>
          </div>
        </div>

        <div className="topbar-status">
          <span className="status-dot" />
          Talent database connected
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
            Search your talent database using natural language.
            Describe the experience, skills, or background you need.
          </p>

          <div className="search-container">
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
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleSearch();
                }
              }}
              placeholder="e.g. Find Python developers with 5+ years of experience"
              aria-label="Candidate search"
            />

            <button
              className="search-button"
              onClick={handleSearch}
              disabled={loading || !query.trim()}
            >
              {loading ? (
                <>
                  <span className="button-spinner" />
                  Searching
                </>
              ) : (
                <>
                  Search
                  <span className="button-arrow">→</span>
                </>
              )}
            </button>
          </div>

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
          </div>
        </section>

        {error && (
          <div className="alert error-alert">
            <div className="alert-icon">!</div>

            <div>
              <strong>Search failed</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        {loading && (
          <section className="loading-state">
            <div className="loading-spinner" />

            <div>
              <strong>Searching your talent database</strong>
              <p>
                Finding candidates that match your requirements...
              </p>
            </div>
          </section>
        )}

        {data && !loading && (
          <section className="results-section">
            <div className="results-header">
              <div>
                <div className="results-title-row">
                  <h2>Search results</h2>

                  <span className="result-count">
                    {resultCount}{" "}
                    {resultCount === 1
                      ? "candidate"
                      : "candidates"}
                  </span>
                </div>

                <div className="query-display">
                  “{data.parsed.original_query}”
                </div>
              </div>

              <div className="search-meta">
                {searchTime !== null && (
                  <span>
                    {searchTime}s
                  </span>
                )}

                <span className="route-badge">
                  <span className="route-dot" />
                  {data.route}
                </span>
              </div>
            </div>

            <div className="requirement-bar">
              {requirements?.skills?.map((skill) => (
                <span
                  className="requirement-pill"
                  key={skill}
                >
                  {skill}
                </span>
              ))}

              {requirements?.experience_min_years !==
                null &&
                requirements?.experience_min_years !==
                  undefined && (
                  <span className="requirement-pill">
                    {requirements.experience_min_years}+ years
                    experience
                  </span>
                )}

              {requirements?.recency_months ? (
                <span className="requirement-pill">
                  Active in last{" "}
                  {requirements.recency_months} months
                </span>
              ) : null}

              {requirements?.role && (
                <span className="requirement-pill">
                  {requirements.role}
                </span>
              )}

              {data.parsed.semantic_requirement && (
                <span className="requirement-pill semantic-pill">
                  Semantic search
                </span>
              )}
            </div>

            {data.message && (
              <div className="result-message">
                <span className="message-icon">✓</span>
                <span>{data.message}</span>
              </div>
            )}

            {isHybrid && (
              <div className="hybrid-info">
                <span className="hybrid-icon">✦</span>
                <span>
                  Structured requirements and semantic relevance
                  were both used for this search.
                </span>
              </div>
            )}

            {resultCount > 0 ? (
              <div className="candidate-list">
                {isStructured &&
                  (
                    data.results as StructuredCandidate[]
                  ).map((candidate) => (
                    <article
                      className="candidate-card"
                      key={candidate.id}
                    >
                      <div className="candidate-main">
                        <div className="avatar">
                          {getInitials(candidate.name)}
                        </div>

                        <div className="candidate-info">
                          <div className="candidate-name-row">
                            <h3>{candidate.name}</h3>

                            <span className="match-badge perfect">
                              <span>✓</span>
                              {candidate.score}% Match
                            </span>
                          </div>

                          {candidate.email && (
                            <div className="candidate-email">
                              {candidate.email}
                            </div>
                          )}

                          {candidate.matched_skills.length >
                            0 && (
                            <div className="skill-list">
                              {candidate.matched_skills.map(
                                (skill) => (
                                  <div
                                    className="skill-item"
                                    key={skill.skill}
                                  >
                                    <span className="skill-name">
                                      {skill.skill}
                                    </span>

                                    <span className="skill-detail">
                                      {formatMonths(
                                        skill.total_months
                                      )}
                                    </span>

                                    <span className="skill-detail">
                                      Last used{" "}
                                      {formatDate(
                                        skill.last_used
                                      )}
                                    </span>
                                  </div>
                                )
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="candidate-actions">
                        <button
                          className="resume-button"
                          onClick={() =>
                            handleViewResume(candidate.id)
                          }
                        >
                          View Resume
                          <span>↗</span>
                        </button>
                      </div>
                    </article>
                  ))}

                {(isSemantic || isHybrid) &&
                  (
                    data.results as SemanticCandidate[]
                  ).map((candidate) => (
                    <article
                      className="candidate-card"
                      key={candidate.id}
                    >
                      <div className="candidate-main">
                        <div className="avatar">
                          {getInitials(candidate.name)}
                        </div>

                        <div className="candidate-info">
                          <div className="candidate-name-row">
                            <h3>{candidate.name}</h3>

                            <span
                              className={`match-badge ${
                                candidate.match_score >= 80
                                  ? "strong"
                                  : candidate.match_score >= 60
                                  ? "medium"
                                  : "weak"
                              }`}
                            >
                              <span>✓</span>
                              {candidate.match_score}% Match
                            </span>
                          </div>

                          {candidate.email && (
                            <div className="candidate-email">
                              {candidate.email}
                            </div>
                          )}

                          {candidate.evidence.length > 0 && (
                            <div className="evidence-preview">
                              <div className="evidence-label">
                                Why they match
                              </div>

                              <p>
                                {candidate.evidence[0].text}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="candidate-actions">
                        <button
                          className="resume-button"
                          onClick={() =>
                            handleViewResume(candidate.id)
                          }
                        >
                          View Resume
                          <span>↗</span>
                        </button>
                      </div>
                    </article>
                  ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-icon">⌕</div>

                <h3>No candidates found</h3>

                <p>
                  Try changing your search criteria or using
                  broader requirements.
                </p>
              </div>
            )}
          </section>
        )}

      </main>
    </div>
  );
}

export default App;