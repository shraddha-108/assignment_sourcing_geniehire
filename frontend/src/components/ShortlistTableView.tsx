import React, { useState } from "react";
import type { Candidate } from "../types/candidate";
import type { ContactStatus } from "../features/contacts/contactTracker";
import type { CandidateEnrollment, Sequence } from "../features/outreach/outreachSequence";

type ShortlistTableViewProps = {
  candidates: Candidate[];
  enrollments: Record<number, CandidateEnrollment>;
  sequences: Sequence[];
  contactsStatus: Record<number, ContactStatus>;
  onUpdateStatus: (candidateId: number, status: ContactStatus) => void;
  onOpenSequenceModal: (candidates: Candidate[]) => void;
  onOpenProfile: (candidate: Candidate) => void;
  onToggleCompare: (candidateId: number) => void;
  compareCandidateIds: number[];
  onNavigateCompare: () => void;
  ownerName?: string;
};

export const ShortlistTableView: React.FC<ShortlistTableViewProps> = ({
  candidates,
  enrollments,
  sequences,
  contactsStatus,
  onUpdateStatus,
  onOpenSequenceModal,
  onOpenProfile,
  onToggleCompare,
  compareCandidateIds,
  onNavigateCompare,
  ownerName = "shraddha",
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [starredIds, setStarredIds] = useState<Set<number>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [sortBy, setSortBy] = useState<"date" | "name" | "role">("date");

  const toggleStar = (id: number) => {
    setStarredIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectCandidate = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === candidates.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(candidates.map((c) => c.id)));
    }
  };

  const filteredCandidates = candidates.filter((c) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    const nameMatch = c.name.toLowerCase().includes(term);
    const company = (c.experience_timeline?.[0]?.company || "").toLowerCase();
    const role = (c.experience_timeline?.[0]?.role || c.headline || "").toLowerCase();
    return nameMatch || company.includes(term) || role.includes(term);
  });

  const getCompanyInitial = (companyName: string) => {
    return companyName.charAt(0).toUpperCase() || "C";
  };

  const getCompanyBgColor = (companyName: string) => {
    const colors = ["#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6"];
    let hash = 0;
    for (let i = 0; i < companyName.length; i++) {
      hash = companyName.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  const selectedCandidatesList = candidates.filter((c) => selectedIds.has(c.id));

  return (
    <div className="shortlist-table-container">
      {/* Breadcrumb Header matching Screenshot 1 */}
      <div className="shortlist-breadcrumb-bar">
        <div className="shortlist-breadcrumb">
          <span>Projects</span>
          <span className="breadcrumb-separator">&gt;</span>
          <span>First Project</span>
          <span className="breadcrumb-separator">&gt;</span>
          <strong className="breadcrumb-current">Shortlist ({candidates.length})</strong>
        </div>
      </div>

      {/* Toolbar matching Screenshot 1 */}
      <div className="shortlist-toolbar">
        <div className="shortlist-search-wrapper">
          <svg className="shortlist-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className="shortlist-search-input"
            placeholder="Search by name, company, etc."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="shortlist-toolbar-actions">
          <select
            className="shortlist-sort-select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
          >
            <option value="date">Sort by Date (Newest)</option>
            <option value="name">Sort by Name</option>
            <option value="role">Sort by Role</option>
          </select>

          <button type="button" className="shortlist-filter-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="4" y1="6" x2="20" y2="6" />
              <line x1="7" y1="12" x2="17" y2="12" />
              <line x1="10" y1="18" x2="14" y2="18" />
            </svg>
            Filter
          </button>

          <button type="button" className="shortlist-action-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            </svg>
            View insights
          </button>

          <button type="button" className="shortlist-action-btn">
            Request review
          </button>

          <button type="button" className="shortlist-more-btn" aria-label="More options">
            •••
          </button>
        </div>
      </div>

      {/* Bulk actions banner if rows selected */}
      {selectedIds.size > 0 && (
        <div className="shortlist-bulk-banner">
          <span>{selectedIds.size} of {candidates.length} selected</span>
          <div className="bulk-actions-group">
            <button
              type="button"
              className="bulk-sequence-btn"
              onClick={() => onOpenSequenceModal(selectedCandidatesList)}
            >
              Add {selectedIds.size} to Sequence
            </button>
            {compareCandidateIds.length >= 2 && (
              <button
                type="button"
                className="bulk-compare-btn"
                onClick={onNavigateCompare}
              >
                Compare ({compareCandidateIds.length})
              </button>
            )}
          </div>
        </div>
      )}

      {/* Shortlist Table */}
      <div className="shortlist-table-responsive">
        <table className="shortlist-table">
          <thead>
            <tr>
              <th className="th-checkbox">
                <input
                  type="checkbox"
                  checked={selectedIds.size === candidates.length && candidates.length > 0}
                  onChange={toggleSelectAll}
                  aria-label="Select all candidates"
                />
              </th>
              <th className="th-name">
                Full Name <span className="sort-indicator">↑↓</span>
              </th>
              <th className="th-profiles">Profiles</th>
              <th className="th-status">
                Status <span className="sort-indicator">↑↓</span>
              </th>
              <th className="th-sequence">Sequence</th>
              <th className="th-owner">Owner</th>
              <th className="th-date">
                Date <span className="sort-indicator">↓</span>
              </th>
              <th className="th-role">Current Role</th>
              <th className="th-org">
                Organization <span className="sort-indicator">↑↓</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredCandidates.map((candidate) => {
              const enrollment = enrollments[candidate.id];
              const sequenceObj = enrollment ? sequences.find((s) => s.id === enrollment.sequenceId) : null;
              const status: ContactStatus = contactsStatus[candidate.id] || "To contact";
              const isStarred = starredIds.has(candidate.id);
              const isChecked = selectedIds.has(candidate.id);

              const currentExperience = candidate.experience_timeline?.[0];
              const roleTitle = currentExperience?.role || candidate.headline || "Software Engineer";
              const companyName = currentExperience?.company || "Tech Innovator";

              return (
                <tr key={candidate.id} className={isChecked ? "row-selected" : ""}>
                  <td className="td-checkbox">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {
                        toggleSelectCandidate(candidate.id);
                        onToggleCompare(candidate.id);
                      }}
                      aria-label={`Select ${candidate.name}`}
                    />
                  </td>
                  <td className="td-name">
                    <div className="name-cell">
                      <button
                        type="button"
                        className="candidate-name-link"
                        onClick={() => onOpenProfile(candidate)}
                      >
                        {candidate.name}
                      </button>
                      <button
                        type="button"
                        className={`star-button ${isStarred ? "starred" : ""}`}
                        onClick={() => toggleStar(candidate.id)}
                        aria-label="Star candidate"
                      >
                        {isStarred ? "★" : "☆"}
                      </button>
                    </div>
                  </td>
                  <td className="td-profiles">
                    <div className="profiles-cell">
                      {candidate.linkedin_url && (
                        <a
                          href={candidate.linkedin_url}
                          target="_blank"
                          rel="noreferrer"
                          className="profile-icon-badge in-badge"
                          title="LinkedIn Profile"
                        >
                          in
                        </a>
                      )}
                      {candidate.email && (
                        <a
                          href={`mailto:${candidate.email}`}
                          className="profile-icon-badge mail-badge"
                          title={candidate.email}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="2" y="4" width="20" height="16" rx="2" />
                            <path d="m22 7-10 7L2 7" />
                          </svg>
                        </a>
                      )}
                      {candidate.github_url && (
                        <a
                          href={candidate.github_url}
                          target="_blank"
                          rel="noreferrer"
                          className="profile-icon-badge github-badge"
                          title="GitHub Profile"
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                          </svg>
                        </a>
                      )}
                      {candidate.phone && (
                        <span className="profile-icon-badge phone-badge" title={candidate.phone}>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                          </svg>
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="td-status">
                    <div className="status-dropdown-wrapper">
                      <span className={`status-dot dot-${status.toLowerCase().replace(/\s+/g, "-")}`} />
                      <select
                        className="table-status-select"
                        value={status}
                        onChange={(e) => onUpdateStatus(candidate.id, e.target.value as ContactStatus)}
                      >
                        <option value="To contact">Not Contacted</option>
                        <option value="Contacted">Contacted</option>
                        <option value="Replied">Replied</option>
                        <option value="Interviewing">Interviewing</option>
                        <option value="Hired">Hired</option>
                        <option value="Not interested">Not interested</option>
                      </select>
                    </div>
                  </td>
                  <td className="td-sequence">
                    {enrollment ? (
                      <button
                        type="button"
                        className="enrolled-sequence-pill"
                        onClick={() => onOpenSequenceModal([candidate])}
                        title={`Enrolled in ${sequenceObj?.name || "Sequence"} (Step ${enrollment.currentStep} of ${sequenceObj?.steps.length || 3})`}
                      >
                        <span className="sequence-lightning">⚡</span>
                        <span className="sequence-label">
                          {sequenceObj?.name.split(" ")[0] || "Outreach"} ({enrollment.currentStep}/{sequenceObj?.steps.length || 3})
                        </span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="add-sequence-button"
                        onClick={() => onOpenSequenceModal([candidate])}
                      >
                        Add +
                      </button>
                    )}
                  </td>
                  <td className="td-owner">
                    <div className="owner-cell">
                      <span className="owner-avatar">👤</span>
                      <span>{ownerName}</span>
                    </div>
                  </td>
                  <td className="td-date">
                    <span className="date-cell">3 days ago</span>
                  </td>
                  <td className="td-role">
                    <span className="role-cell" title={roleTitle}>
                      {roleTitle}
                    </span>
                  </td>
                  <td className="td-org">
                    <div className="org-cell">
                      <span
                        className="org-icon"
                        style={{ backgroundColor: getCompanyBgColor(companyName) }}
                      >
                        {getCompanyInitial(companyName)}
                      </span>
                      <span className="org-name" title={companyName}>
                        {companyName}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
