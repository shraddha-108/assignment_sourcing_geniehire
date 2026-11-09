import type { SearchResponse, StructuredRequirements } from "../types/candidate";

type SearchResultSummaryProps = {
  data: SearchResponse;
  resultCount: number;
  searchTime: number | null;
  requirements?: StructuredRequirements;
  semanticCriteria: string[];
  temporalCriteria: NonNullable<SearchResponse["parsed"]["requirements"]>;
  seniorityPolicy: StructuredRequirements["seniority_filter"];
  formatSeniorityRange: (minMonths: number, maxMonths: number | null) => string;
};

export function SearchResultSummary({
  data, resultCount, searchTime, requirements, semanticCriteria, temporalCriteria, seniorityPolicy, formatSeniorityRange,
}: SearchResultSummaryProps) {
  return (
    <>
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

                {seniorityPolicy && (
                  <>
                    <span className="requirement-pill">
                      {seniorityPolicy.seniority.replaceAll("_", " ")} seniority
                    </span>
                    <span className="requirement-pill">
                      Preferred: {formatSeniorityRange(
                        seniorityPolicy.preferred_min_months,
                        seniorityPolicy.preferred_max_months
                      )}
                    </span>
                    <span className="requirement-pill">
                      Acceptable: {formatSeniorityRange(
                        seniorityPolicy.acceptable_min_months,
                        seniorityPolicy.acceptable_max_months
                      )}
                    </span>
                    <span className="requirement-pill">
                      Based on {seniorityPolicy.experience_scope === "RELEVANT_ROLE"
                        ? "relevant role experience"
                        : "overall experience"}
                    </span>
                  </>
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
    </>
  );
}
