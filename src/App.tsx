import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/search";

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

type SemanticCandidate = {
  id: number;
  name: string;
  email: string | null;
  score: number;
  evidence_type: string | null;
  evidence: string | null;
  similarity: number;
};

type StructuredRequirements = {
  skills: string[];
  recency_months: number | null;
  experience_min_years: number | null;
};

type RoutingPacket = {
  original_query: string;
  requested_count: number;
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

function App() {
  const [query, setQuery] = useState("");
  const [data, setData] =
    useState<SearchResponse | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleSearch() {
    if (!query.trim()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        API_URL,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            query,
          }),
        }
      );

      if (!res.ok) {
        throw new Error(
          `Server error (${res.status})`
        );
      }

      const response =
        await res.json();

      if (response.valid === false) {
        setError(
          response.errors?.join(", ") ||
            "Invalid query"
        );

        setData(null);
        return;
      }

      setData(response);
    } catch (e) {
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

  const requirements =
    data?.parsed
      ?.structured_requirements;

  const isStructured =
    data?.route === "STRUCTURED";

  const isSemantic =
    data?.route === "SEMANTIC";

  return (
    <div className="page">

      <h1>
        Recruiter Intelligence Search
      </h1>

      <div className="search-row">

        <input
          value={query}
          onChange={(e) =>
            setQuery(e.target.value)
          }
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              handleSearch();
            }
          }}
          placeholder="Find candidates who recently worked with Python"
        />

        <button
          onClick={handleSearch}
          disabled={loading}
        >
          {loading
            ? "Searching..."
            : "Search"}
        </button>

      </div>

      {error && (
        <p className="error">
          {error}
        </p>
      )}

      {data && (
        <p className="hint">

          Route:{" "}
          <strong>
            {data.route}
          </strong>

          {requirements?.skills
            ?.length
            ? ` · Skills: ${requirements.skills.join(", ")}`
            : ""}

          {requirements?.recency_months
            ? ` · Last ${requirements.recency_months} months`
            : ""}

          {` · Showing ${data.results.length}`}

        </p>
      )}

      {data?.message && (
        <p className="hint">
          {data.message}
        </p>
      )}

      <div className="results">

        {isStructured &&
          (
            data.results as StructuredCandidate[]
          ).map((candidate) => (

            <div
              className="card"
              key={candidate.id}
            >

              <div className="card-head">

                <strong>
                  {candidate.name}
                </strong>

                <span className="score">
                  Score {candidate.score}
                </span>

              </div>

              {candidate.email && (
                <div className="email">
                  {candidate.email}
                </div>
              )}

              <ul>

                {candidate.matched_skills.map(
                  (skill) => (

                    <li
                      key={skill.skill}
                    >
                      {skill.skill}: last used{" "}
                      {skill.last_used},{" "}
                      {skill.total_months}{" "}
                      months total
                    </li>

                  )
                )}

              </ul>

            </div>

          ))}

        {isSemantic &&
          (
            data.results as SemanticCandidate[]
          ).map((candidate) => (

            <div
              className="card"
              key={candidate.id}
            >

              <div className="card-head">

                <strong>
                  {candidate.name}
                </strong>

                <span className="score">
                  Match {candidate.score}
                </span>

              </div>

              {candidate.email && (
                <div className="email">
                  {candidate.email}
                </div>
              )}

              <div className="email">
                Evidence type:{" "}
                {candidate.evidence_type ||
                  "unknown"}
              </div>

              <p>
                {candidate.evidence ||
                  "No evidence available."}
              </p>

            </div>

          ))}

      </div>

      {data &&
        data.results.length === 0 &&
        !data.message && (
          <p className="hint">
            No candidates matched.
          </p>
        )}

    </div>
  );
}

export default App;