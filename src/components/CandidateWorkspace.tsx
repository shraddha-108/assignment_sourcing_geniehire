import type { Dispatch, MutableRefObject, RefObject, SetStateAction } from "react";
import { CONTACT_STATUSES, type ContactRecord, type ContactStatus } from "../features/contacts/contactTracker";
import { getCandidateDisplayMatchStatus } from "../features/candidates/candidateWorkflow";
import type { Candidate, CandidateView, ContactCandidate, StructuredRequirements } from "../types/candidate";
import { buildMailtoLink, formatMonths, getInitials, normalizeExternalUrl } from "../features/candidates/candidatePresentation";
import { CandidateCard } from "./CandidateCard";

type CandidateWorkspaceState = {
  candidateView: CandidateView;
  shortlistedCandidates: Candidate[];
  hiddenCandidates: Candidate[];
  contacts: ContactRecord<ContactCandidate>[];
  contactsStorageError: string | null;
  compareCandidateIds: number[];
  outreachCandidateIds: number[];
  outreachSubject: string;
  outreachMessage: string;
};

type CandidateWorkspaceData = {
  visibleResultCandidates: Candidate[];
  activeCandidates: Candidate[];
  compareCandidates: Candidate[];
  outreachCandidates: Candidate[];
  searchQuery: string;
  requirements?: StructuredRequirements;
  seniorityPolicy: StructuredRequirements["seniority_filter"];
};

type CandidateWorkspaceActions = {
  navigateCandidateView: (view: CandidateView, resetNext?: boolean) => void;
  openProfile: (candidate: Candidate) => void;
  updateContactStatus: (candidateId: number, status: ContactStatus) => void;
  removeContact: (candidateId: number) => void;
  setOutreachCandidateIds: Dispatch<SetStateAction<number[]>>;
  continueToOutreach: () => void;
  setOutreachSubject: Dispatch<SetStateAction<string>>;
  setOutreachMessage: Dispatch<SetStateAction<string>>;
  toggleCompare: (candidateId: number) => void;
  hideCandidate: (candidate: Candidate) => void;
  restoreCandidate: (candidateId: number) => void;
  toggleShortlist: (candidate: Candidate) => void;
};

type CandidateWorkspaceProps = {
  state: CandidateWorkspaceState;
  data: CandidateWorkspaceData;
  actions: CandidateWorkspaceActions;
  tabScrollRef: RefObject<HTMLDivElement | null>;
  tabScrollPositionsRef: MutableRefObject<Partial<Record<CandidateView, number>>>;
};

export function CandidateWorkspace({ state, data, actions, tabScrollRef, tabScrollPositionsRef }: CandidateWorkspaceProps) {
  const { candidateView, shortlistedCandidates, hiddenCandidates, contacts, contactsStorageError, compareCandidateIds, outreachSubject, outreachMessage, outreachCandidateIds } = state;
  const { visibleResultCandidates, activeCandidates, compareCandidates, outreachCandidates, requirements, seniorityPolicy, searchQuery } = data;
  const { navigateCandidateView, openProfile, updateContactStatus, removeContact, setOutreachCandidateIds, continueToOutreach, setOutreachSubject, setOutreachMessage, toggleCompare, hideCandidate, restoreCandidate, toggleShortlist } = actions;
  return (
                  <div className="results-list-column">
                    <div className="candidate-view-toolbar">
                      <div className="candidate-view-tabs" aria-label="Candidate lists">
                        <button
                          type="button"
                          className={candidateView === "results" ? "active" : ""}
                          aria-pressed={candidateView === "results"}
                          onClick={() => navigateCandidateView("results")}
                        >
                          Results <span>{visibleResultCandidates.length}</span>
                        </button>
                        <button
                          type="button"
                          className={candidateView === "shortlist" || candidateView === "compare" || candidateView === "outreach" ? "active" : ""}
                          aria-pressed={candidateView === "shortlist" || candidateView === "compare" || candidateView === "outreach"}
                          onClick={() => navigateCandidateView("shortlist")}
                        >
                          Shortlist <span>{shortlistedCandidates.length}</span>
                        </button>
                        <button
                          type="button"
                          className={candidateView === "contacts" ? "active" : ""}
                          aria-pressed={candidateView === "contacts"}
                          onClick={() => navigateCandidateView("contacts")}
                        >
                          Contacts <span>{contacts.length}</span>
                        </button>
                        <button
                          type="button"
                          className={candidateView === "hidden" ? "active" : ""}
                          aria-pressed={candidateView === "hidden"}
                          onClick={() => navigateCandidateView("hidden")}
                        >
                          Hidden <span>{hiddenCandidates.length}</span>
                        </button>
                      </div>
                      {candidateView === "shortlist" && (
                        <div className="shortlist-controls">
                          <span>{compareCandidateIds.length} selected · choose 2–4 to compare</span>
                          <button
                            type="button"
                            className="candidate-action-button candidate-action-primary"
                            disabled={compareCandidates.length < 2}
                            onClick={() => navigateCandidateView("compare")}
                          >
                            Compare{compareCandidateIds.length ? ` (${compareCandidateIds.length})` : ""}
                          </button>
                        </div>
                      )}
                    </div>

                    <div
                      className="candidate-tab-scroll"
                      ref={tabScrollRef}
                      onScroll={(event) => {
                        tabScrollPositionsRef.current[candidateView] = event.currentTarget.scrollTop;
                      }}
                    >
                    {candidateView === "contacts" ? (
                      <section className="contacts-view">
                        <div className="comparison-heading">
                          <div>
                            <span className="workflow-eyebrow">CANDIDATE PIPELINE</span>
                            <h3>Contacts</h3>
                            <p>Track who you plan to contact and what happened next. Opening a draft does not mark it as sent.</p>
                          </div>
                        </div>
                        {contactsStorageError && (
                          <p className="contacts-storage-error" role="alert">{contactsStorageError}</p>
                        )}
                        {contacts.length ? (
                          <div className="contacts-list">
                            {contacts.map((contact) => {
                              const candidate = contact.candidate;
                              return (
                                <article className="contact-row" key={candidate.id}>
                                  <span className="avatar">{getInitials(candidate.name)}</span>
                                  <div className="contact-row-info">
                                    <strong>{candidate.name}</strong>
                                    <span>{candidate.email || candidate.phone || "No email or phone on profile"}</span>
                                    <small>
                                      {contact.sourceQuery ? `From: ${contact.sourceQuery} · ` : ""}
                                      {contact.contactedAt
                                        ? `Contacted ${new Date(contact.contactedAt).toLocaleDateString()}`
                                        : `Added ${new Date(contact.addedAt).toLocaleDateString()}`}
                                    </small>
                                  </div>
                                  <label className="contact-status-control">
                                    <span>Status</span>
                                    <select
                                      value={contact.status}
                                      aria-label={`${candidate.name} contact status`}
                                      onChange={(event) => updateContactStatus(candidate.id, event.target.value as ContactStatus)}
                                    >
                                      {CONTACT_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
                                    </select>
                                  </label>
                                  {candidate.email && (
                                    <a
                                      className="candidate-action-button"
                                      href={buildMailtoLink(
                                        candidate.email,
                                        outreachSubject.replaceAll("{{firstName}}", candidate.name.split(/\s+/)[0] ?? candidate.name),
                                        outreachMessage
                                          .replaceAll("{{firstName}}", candidate.name.split(/\s+/)[0] ?? candidate.name)
                                          .replaceAll("{{searchQuery}}", contact.sourceQuery ?? "our open role")
                                      )}
                                    >
                                      Draft email
                                    </a>
                                  )}
                                  {normalizeExternalUrl(candidate.linkedin_url) && (
                                    <a
                                      className="candidate-action-button"
                                      href={normalizeExternalUrl(candidate.linkedin_url) ?? undefined}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                    >
                                      LinkedIn
                                    </a>
                                  )}
                                  {candidate.phone && (
                                    <a className="candidate-action-button" href={`tel:${candidate.phone}`}>
                                      Call
                                    </a>
                                  )}
                                  <button
                                    type="button"
                                    className="outreach-remove-button"
                                    aria-label={`Remove ${candidate.name} from contacts`}
                                    title="Remove from contacts"
                                    onClick={() => removeContact(candidate.id)}
                                  >
                                    ×
                                  </button>
                                </article>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="outreach-empty">
                            No contacts yet. Compare shortlisted candidates and continue to outreach to add finalists here.
                          </div>
                        )}
                        <p className="contacts-storage-note">Contacts are saved in this browser on this device.</p>
                      </section>
                    ) : candidateView === "outreach" ? (
                      <section className="outreach-view">
                        <div className="comparison-heading">
                          <div>
                            <span className="workflow-eyebrow">FINAL STEP</span>
                            <h3>Outreach your finalists</h3>
                            <p>Review the note, then open a separate email draft for each candidate. Nothing is sent without your approval.</p>
                          </div>
                          <button
                            type="button"
                            className="candidate-action-button"
                            onClick={() => navigateCandidateView("compare")}
                          >
                            ← Back to comparison
                          </button>
                        </div>

                        <div className="outreach-layout">
                          <div className="outreach-recipients">
                          {contactsStorageError && (
                            <p className="contacts-storage-error" role="alert">{contactsStorageError}</p>
                          )}
                          <div className="outreach-section-heading">
                              <div>
                                <strong>Selected candidates</strong>
                                <span>{outreachCandidates.length} finalist{outreachCandidates.length === 1 ? "" : "s"}</span>
                              </div>
                              <button
                                type="button"
                                onClick={() => setOutreachCandidateIds(compareCandidates.map((candidate) => candidate.id))}
                                disabled={outreachCandidateIds.length === compareCandidates.length}
                              >
                                Reset selection
                              </button>
                            </div>
                            {outreachCandidates.length ? outreachCandidates.map((candidate) => (
                              <article className="outreach-recipient" key={candidate.id}>
                                <span className="avatar">{getInitials(candidate.name)}</span>
                                <div className="outreach-recipient-info">
                                  <strong>{candidate.name}</strong>
                                  {candidate.email
                                    ? <span>{candidate.email}</span>
                                    : <span className="outreach-no-email">No email on profile</span>}
                                </div>
                                {candidate.email ? (
                                  <a
                                    className="candidate-action-button candidate-action-primary outreach-send-button"
                                    href={buildMailtoLink(
                                      candidate.email,
                                      outreachSubject.replaceAll("{{firstName}}", candidate.name.split(/\s+/)[0] ?? candidate.name),
                                      outreachMessage
                                        .replaceAll("{{firstName}}", candidate.name.split(/\s+/)[0] ?? candidate.name)
                                        .replaceAll("{{searchQuery}}", searchQuery || "our open role")
                                    )}
                                  >
                                    Open email draft <span aria-hidden="true">↗</span>
                                  </a>
                                ) : normalizeExternalUrl(candidate.linkedin_url) ? (
                                  <a
                                    className="candidate-action-button outreach-link-button"
                                    href={normalizeExternalUrl(candidate.linkedin_url) ?? undefined}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    LinkedIn <span aria-hidden="true">↗</span>
                                  </a>
                                ) : candidate.phone ? (
                                  <a className="candidate-action-button outreach-link-button" href={`tel:${candidate.phone}`}>
                                    Call
                                  </a>
                                ) : (
                                  <span className="outreach-unavailable">No contact link</span>
                                )}
                                <label className="outreach-status-control">
                                  <span className="sr-only">{candidate.name} contact status</span>
                                  <select
                                    aria-label={`${candidate.name} contact status`}
                                    value={contacts.find((contact) => contact.candidate.id === candidate.id)?.status ?? "To contact"}
                                    onChange={(event) => updateContactStatus(candidate.id, event.target.value as ContactStatus)}
                                  >
                                    {CONTACT_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
                                  </select>
                                </label>
                                {(contacts.find((contact) => contact.candidate.id === candidate.id)?.status ?? "To contact") === "To contact" && (
                                  <button
                                    type="button"
                                    className="contact-mark-button"
                                    onClick={() => updateContactStatus(candidate.id, "Contacted")}
                                  >
                                    Mark contacted
                                  </button>
                                )}
                                <button
                                  type="button"
                                  className="outreach-remove-button"
                                  aria-label={`Remove ${candidate.name} from outreach`}
                                  onClick={() => setOutreachCandidateIds((current) =>
                                    current.filter((id) => id !== candidate.id)
                                  )}
                                >
                                  ×
                                </button>
                              </article>
                            )) : (
                              <div className="outreach-empty">
                                No candidates selected. Go back to comparison and select your finalists.
                              </div>
                            )}
                          </div>

                          <div className="outreach-composer">
                            <div className="outreach-section-heading">
                              <div>
                                <strong>Email template</strong>
                                <span>Personalized draft, one candidate at a time</span>
                              </div>
                            </div>
                            <label>
                              Subject
                              <input
                                value={outreachSubject}
                                onChange={(event) => setOutreachSubject(event.target.value)}
                                aria-label="Outreach email subject"
                              />
                            </label>
                            <label>
                              Message
                              <textarea
                                value={outreachMessage}
                                onChange={(event) => setOutreachMessage(event.target.value)}
                                aria-label="Outreach email message"
                                rows={11}
                              />
                            </label>
                            <p className="outreach-template-hint">
                              Use <code>{"{{firstName}}"}</code> and <code>{"{{searchQuery}}"}</code> to personalize each draft.
                              {" "}Drafts open in your email app; update a candidate’s status only after taking that action.
                            </p>
                          </div>
                        </div>
                      </section>
                    ) : candidateView === "compare" ? (
                      <section className="comparison-view">
                        <div className="comparison-heading">
                          <div>
                            <h3>Compare shortlisted candidates</h3>
                            <p>Review the essentials side by side.</p>
                          </div>
                          <button
                            type="button"
                            className="candidate-action-button"
                            onClick={() => navigateCandidateView("shortlist")}
                          >
                            Back to shortlist
                          </button>
                        </div>
                        {compareCandidates.length >= 2 ? (
                          <>
                            <div className="comparison-scroll">
                              <table className="comparison-table">
                              <thead>
                                <tr>
                                  <th scope="col">Criteria</th>
                                  {compareCandidates.map((candidate) => (
                                    <th scope="col" key={candidate.id}>
                                      <div className="comparison-candidate">
                                        <span className="avatar">{getInitials(candidate.name)}</span>
                                        <strong>{candidate.name}</strong>
                                        <button type="button" onClick={() => openProfile(candidate)}>
                                          View profile
                                        </button>
                                      </div>
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <th scope="row">Experience</th>
                                  {compareCandidates.map((candidate) => (
                                    <td key={candidate.id}>
                                      {candidate.total_experience_months == null
                                        ? "Not listed"
                                        : formatMonths(candidate.total_experience_months)}
                                    </td>
                                  ))}
                                </tr>
                                <tr>
                                  <th scope="row">Current role</th>
                                  {compareCandidates.map((candidate) => {
                                    const currentRole =
                                      candidate.experience_timeline.find((item) => item.is_current) ??
                                      candidate.experience_timeline[0];
                                    return (
                                      <td key={candidate.id}>
                                        {currentRole?.role ?? candidate.headline ?? "Not listed"}
                                        {currentRole?.company ? ` · ${currentRole.company}` : ""}
                                      </td>
                                    );
                                  })}
                                </tr>
                                <tr>
                                  <th scope="row">Location</th>
                                  {compareCandidates.map((candidate) => (
                                    <td key={candidate.id}>{candidate.location ?? "Not listed"}</td>
                                  ))}
                                </tr>
                                <tr>
                                  <th scope="row">Match</th>
                                  {compareCandidates.map((candidate) => (
                                    <td key={candidate.id}>
                                      {getCandidateDisplayMatchStatus(
                                        candidate.match_status,
                                        candidate.matched_requirements
                                      ) === "MATCH" ? "Match" : "Partial match"}
                                    </td>
                                  ))}
                                </tr>
                                <tr>
                                  <th scope="row">Found in searches</th>
                                  {compareCandidates.map((candidate) => (
                                    <td key={candidate.id}>
                                      {candidate.shortlistSourceQueries?.join(" · ") || "Current search"}
                                    </td>
                                  ))}
                                </tr>
                                <tr>
                                  <th scope="row">Key skills</th>
                                  {compareCandidates.map((candidate) => (
                                    <td key={candidate.id}>
                                      {[...new Set([
                                        ...candidate.profile_skills,
                                        ...candidate.matched_skills.map((item) => item.skill),
                                      ])].slice(0, 6).join(", ") || "Not listed"}
                                    </td>
                                  ))}
                                </tr>
                                <tr>
                                  <th scope="row">Education</th>
                                  {compareCandidates.map((candidate) => {
                                    const education = candidate.education[0];
                                    return (
                                      <td key={candidate.id}>
                                        {education
                                          ? [education.degree, education.field_of_study, education.institution]
                                              .filter(Boolean)
                                              .join(" · ")
                                          : "Not listed"}
                                      </td>
                                    );
                                  })}
                                </tr>
                                <tr>
                                  <th scope="row">Matching evidence</th>
                                  {compareCandidates.map((candidate) => {
                                    const matches = candidate.matched_requirements
                                      .filter((item) => item.matched)
                                      .slice(0, 3)
                                      .map((item) => item.requirement);
                                    return <td key={candidate.id}>{matches.join(", ") || "Review profile"}</td>;
                                  })}
                                </tr>
                              </tbody>
                              </table>
                            </div>
                            <div className="comparison-next-step">
                              <p>
                                Ready to contact your finalists? We’ll prepare an individual email draft for each selected candidate.
                              </p>
                              <button
                                type="button"
                                className="candidate-action-button candidate-action-primary"
                                disabled={compareCandidates.length < 2}
                                onClick={continueToOutreach}
                              >
                                Continue to outreach <span aria-hidden="true">→</span>
                              </button>
                            </div>
                          </>
                        ) : (
                          <div className="filter-empty-state">
                            Select at least two candidates from your shortlist to compare.
                          </div>
                        )}
                      </section>
                    ) : activeCandidates.length ? (
                      <div className="candidate-list">
                  {activeCandidates.map((candidate) => (
                    <CandidateCard
                      key={candidate.id}
                      candidate={candidate}
                      candidateView={candidateView}
                      requirements={requirements}
                      seniorityPolicy={seniorityPolicy}
                      isShortlisted={shortlistedCandidates.some((item) => item.id === candidate.id)}
                      compareSelected={compareCandidateIds.includes(candidate.id)}
                      compareDisabled={!compareCandidateIds.includes(candidate.id) && compareCandidateIds.length >= 4}
                      onToggleCompare={toggleCompare}
                      onHide={hideCandidate}
                      onRestore={restoreCandidate}
                      onToggleShortlist={toggleShortlist}
                      onOpenProfile={openProfile}
                    />
                  ))}
                      </div>
                    ) : (
                      <div className="filter-empty-state">
                        <strong>
                          {candidateView === "shortlist"
                            ? "Your shortlist is empty"
                            : candidateView === "hidden"
                              ? "No hidden candidates"
                              : "No candidates found"}
                        </strong>
                        <p>
                          {candidateView === "shortlist"
                            ? "Shortlist candidates from Results to keep your strongest matches together."
                            : candidateView === "hidden"
                              ? "Candidates you hide will appear here, and you can restore them anytime."
                              : "Try changing the search or adjusting the applied filters."}
                        </p>
                      </div>
                    )}
                    </div>
                  </div>
  );
}
