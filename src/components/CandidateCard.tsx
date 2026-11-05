import { getCandidateDisplayMatchStatus } from "../features/candidates/candidateWorkflow";
import type { Candidate, CandidateView, Evidence, StructuredRequirements } from "../types/candidate";
import {
  conciseEvidenceText,
  evidenceSectionLabel,
  formatMonths,
  formatTimelineDate,
  getInitials,
  groupMatchedRequirements,
} from "../features/candidates/candidatePresentation";

type CandidateCardProps = {
  candidate: Candidate;
  candidateView: CandidateView;
  requirements?: StructuredRequirements;
  seniorityPolicy: StructuredRequirements["seniority_filter"];
  isShortlisted: boolean;
  compareSelected: boolean;
  compareDisabled: boolean;
  onToggleCompare: (candidateId: number) => void;
  onHide: (candidate: Candidate) => void;
  onRestore: (candidateId: number) => void;
  onToggleShortlist: (candidate: Candidate) => void;
  onOpenProfile: (candidate: Candidate) => void;
};

export function CandidateCard({
  candidate, candidateView, requirements, seniorityPolicy, isShortlisted, compareSelected, compareDisabled,
  onToggleCompare, onHide, onRestore, onToggleShortlist, onOpenProfile,
}: CandidateCardProps) {
                        const shownProofs = new Set<string>();
                      const candidateMatchStatus = getCandidateDisplayMatchStatus(
                        candidate.match_status,
                        candidate.matched_requirements
                      );
                      const unverifiedRelevantExperience = candidate.matched_requirements.find(
                        (match) => match.type === "relevant_experience" && !match.matched
                      );
                      const displayedRequirements = groupMatchedRequirements(
                        candidate.matched_requirements
                      );
                      const partialRequirements = displayedRequirements.filter(
                        (match) => match.status === "PARTIAL_MATCH" && match.partial_reason
                      );
                      const evidenceRequirements = displayedRequirements.filter(
                        (match) => match.matched || match.status === "PARTIAL_MATCH"
                      );
                      const partialNote =
                        partialRequirements[0]?.partial_reason ??
                        (unverifiedRelevantExperience
                          ? "Related experience was found, but its requested duration could not be confirmed from dated work history."
                          : null);
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
                                <span className={`candidate-match-status ${candidateMatchStatus === "PARTIAL_MATCH" ? "partial" : "complete"}`}>
                                  <span className="match-status-icon" aria-hidden="true">
                                    {candidateMatchStatus === "PARTIAL_MATCH" ? "!" : "✓"}
                                  </span>
                                  {candidateMatchStatus === "PARTIAL_MATCH" ? "Partial match" : "Match"}
                                </span>
                              </div>

                              {candidateView === "shortlist" &&
                                candidate.shortlistSourceQueries?.length ? (
                                <div className="shortlist-source">
                                  From search: {candidate.shortlistSourceQueries[0]}
                                  {candidate.shortlistSourceQueries.length > 1 &&
                                    ` · also found in ${candidate.shortlistSourceQueries.length - 1} other ${candidate.shortlistSourceQueries.length === 2 ? "search" : "searches"}`}
                                </div>
                              ) : null}

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
                                  <strong>Best matching role record:</strong>{" "}
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

                              {partialNote && (
                                <div className="candidate-partial-note">{partialNote}</div>
                              )}

                              {evidenceRequirements.length > 0 && (
                                <details className="candidate-evidence-disclosure">
                                  <summary>
                                    <span>
                                      {candidateMatchStatus === "PARTIAL_MATCH"
                                        ? "Why this is a partial match"
                                        : "Why this candidate matches"}
                                    </span>
                                    <span className="candidate-evidence-count">
                                      {evidenceRequirements.length} criteria
                                    </span>
                                  </summary>
                                  <div className="evidence-preview">
                                    {evidenceRequirements
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
                                                    : match.type === "seniority"
                                                      ? `${match.experience_scope === "RELEVANT_ROLE"
                                                        ? `Relevant experience across ${(seniorityPolicy?.role_titles ?? requirements?.roles ?? []).join(", ") || "matching roles"}`
                                                        : "Overall professional experience"}: ${match.candidate_value ?? "not listed"}${match.seniority_fit ? ` (${match.seniority_fit.toLocaleLowerCase()} range)` : ""}.`
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
                                </details>
                              )}
                            </div>
                          </div>

                          <div className="candidate-actions">
                            {candidateView === "shortlist" && (
                              <label className="compare-select">
                                <input
                                  type="checkbox"
                                  checked={compareSelected}
                                  disabled={
                                    !compareSelected &&
                                    compareDisabled
                                  }
                                  onChange={() => onToggleCompare(candidate.id)}
                                />
                                Compare
                              </label>
                            )}
                            {candidateView === "results" && (
                              <button
                                type="button"
                                className="candidate-action-button candidate-action-quiet"
                                onClick={() => onHide(candidate)}
                              >
                                Hide
                              </button>
                            )}
                            {candidateView === "hidden" && (
                              <button
                                type="button"
                                className="candidate-action-button candidate-action-quiet"
                                onClick={() => onRestore(candidate.id)}
                              >
                                Restore
                              </button>
                            )}
                            <button
                              type="button"
                              className={`candidate-action-button shortlist-star-button${isShortlisted ? " is-selected" : ""}`}
                              aria-label={isShortlisted ? `Remove ${candidate.name} from shortlist` : `Add ${candidate.name} to shortlist`}
                              title={isShortlisted ? "Remove from shortlist" : "Add to shortlist"}
                              aria-pressed={isShortlisted}
                              onClick={() => onToggleShortlist(candidate)}
                            >
                              <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="m12 3 2.75 5.57 6.15.89-4.45 4.34 1.05 6.12L12 17.03l-5.5 2.89 1.05-6.12L3.1 9.46l6.15-.89L12 3Z" />
                              </svg>
                              <span>{isShortlisted ? "Shortlisted" : "Shortlist"}</span>
                            </button>
                            <button
                              type="button"
                              className="candidate-action-button candidate-action-quiet"
                              onClick={() => onOpenProfile(candidate)}
                            >
                              View profile <span aria-hidden="true">↗</span>
                            </button>
                          </div>
                        </article>
                      );
}
