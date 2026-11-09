type SearchHeroProps = {
  query: string;
  loading: boolean;
  suggestedQuery: string | null;
  onQueryChange: (value: string) => void;
  onClearSuggestion: () => void;
  onSubmit: () => void;
  onSearchSuggestion: (value: string) => void;
  onSearchOriginal: () => void;
};

export function SearchHero({
  query, loading, suggestedQuery, onQueryChange, onClearSuggestion, onSubmit,
  onSearchSuggestion, onSearchOriginal,
}: SearchHeroProps) {
  return (
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
              onSubmit();
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
                  onQueryChange(e.target.value);
                  onClearSuggestion();
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
              <span>Did you mean</span>
              <strong className="spelling-suggestion-query">{suggestedQuery}?</strong>
              <button
                className="spelling-suggestion-correction"
                type="button"
                onClick={() => {
                  onQueryChange(suggestedQuery);
                  onSearchSuggestion(suggestedQuery);
                }}
              >
                Search suggested query
              </button>
              <button
                className="spelling-suggestion-original"
                type="button"
                onClick={() => onSearchOriginal()}
              >
                Keep original
              </button>
            </div>
          )}

          <div className="search-examples">
            <span>Try:</span>

            <button
              onClick={() =>
                onQueryChange(
                  "Find Python developers with 5+ years of experience"
                )
              }
            >
              Python developers
            </button>

            <button
              onClick={() =>
                onQueryChange(
                  "Find candidates with experience in financial transformation"
                )
              }
            >
              Financial transformation
            </button>

            <button
              onClick={() =>
                onQueryChange(
                  "Find React and Node.js developers"
                )
              }
            >
              React + Node.js
            </button>

            <button
              onClick={() =>
                onQueryChange(
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
  );
}
