import { useState } from "react";
import "./App.css";

const API_URL = "http://localhost:8000/search";

type MatchedSkill = {
  skill: string;
  last_used: string;
  total_months: number;
};

type Candidate = {
  id: number;
  name: string;
  email: string | null;
  score: number;
  matched_skills: MatchedSkill[];
};

type SearchResponse = {
  parsed: { skills: string[]; recency_months: number | null; limit: number };
  results: Candidate[];
  message?: string;
};

function App() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      setData(await res.json());
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong. Is the backend running?"
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <h1>Recruiter Intelligence Search</h1>

      <div className="search-row">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="Find candidates who recently worked with Python"
        />
        <button onClick={handleSearch} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {data?.message && <p className="hint">{data.message}</p>}

      {data && data.results.length > 0 && (
        <p className="hint">
          Skills: {data.parsed.skills.join(", ")}
          {data.parsed.recency_months
            ? ` · used in the last ${data.parsed.recency_months} months`
            : ""}
          {` · showing ${data.results.length}`}
        </p>
      )}

      <div className="results">
        {data?.results.map((c) => (
          <div className="card" key={c.id}>
            <div className="card-head">
              <strong>{c.name}</strong>
              <span className="score">Score {c.score}</span>
            </div>
            {c.email && <div className="email">{c.email}</div>}
            <ul>
              {c.matched_skills.map((s) => (
                <li key={s.skill}>
                  {s.skill}: last used {s.last_used}, {s.total_months} months total
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {data && data.results.length === 0 && !data.message && (
        <p className="hint">No candidates matched.</p>
      )}
    </div>
  );
}

export default App;