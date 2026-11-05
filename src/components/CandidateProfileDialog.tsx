import type { Candidate } from "../types/candidate";
import { formatMonths, formatTimelineDate, getInitials, normalizeExternalUrl } from "../features/candidates/candidatePresentation";

export type ProfileTab = "overview" | "experience" | "projects" | "education" | "skills";

type CandidateProfileDialogProps = {
  candidate: Candidate | null;
  profileTab: ProfileTab;
  onProfileTabChange: (tab: ProfileTab) => void;
  onClose: () => void;
  onViewResume: (candidateId: number) => void;
};

export function CandidateProfileDialog({
  candidate, profileTab, onProfileTabChange, onClose, onViewResume,
}: CandidateProfileDialogProps) {
  const profileLinkedInUrl = normalizeExternalUrl(candidate?.linkedin_url);
  const profileGitHubUrl = normalizeExternalUrl(candidate?.github_url);
  const profilePortfolioUrl = normalizeExternalUrl(candidate?.portfolio_url);
  return (
    <>
      {candidate && (
        <div className="profile-backdrop" onMouseDown={onClose}>
          <aside
            className="profile-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="profile-name"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
            }}
          >
            <div className="profile-panel-topbar">
              <span>Candidate profile</span>
              <button className="profile-close" onClick={onClose} aria-label="Close profile">×</button>
            </div>
            <header className="profile-header">
              <div className="avatar">{getInitials(candidate.name)}</div>
              <div className="profile-heading">
                <h2 id="profile-name">{candidate.name}</h2>
                {candidate.headline && <p>{candidate.headline}</p>}
                {candidate.location && <p>{candidate.location}</p>}
              </div>
            </header>
            <div className="profile-links">
              {profileLinkedInUrl && <a href={profileLinkedInUrl} target="_blank" rel="noopener noreferrer">LinkedIn ↗</a>}
              {profileGitHubUrl && <a href={profileGitHubUrl} target="_blank" rel="noopener noreferrer">GitHub ↗</a>}
              {profilePortfolioUrl && <a href={profilePortfolioUrl} target="_blank" rel="noopener noreferrer">Portfolio ↗</a>}
              <button className="profile-resume-button" onClick={() => onViewResume(candidate.id)}>View resume ↗</button>
            </div>
            <nav className="profile-tabs" aria-label="Candidate profile sections">
              {(["overview", "experience", "projects", "education", "skills"] as const).map((tab) => (
                <button key={tab} className={profileTab === tab ? "active" : ""} onClick={() => onProfileTabChange(tab)}>
                  {tab[0].toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </nav>
            <div className="profile-content">
              <div className="profile-tab-panel" data-tab="overview" hidden={profileTab !== "overview"}>
                <section className="profile-section">
                  <h3>Contact</h3>
                  {candidate.email && <p><span>Email</span><a href={`mailto:${candidate.email}`}>{candidate.email}</a></p>}
                  {candidate.phone && <p><span>Phone</span><a href={`tel:${candidate.phone}`}>{candidate.phone}</a></p>}
                  {!candidate.email && !candidate.phone && <p className="profile-muted">No contact details available.</p>}
                </section>
                {candidate.summary && <section className="profile-section"><h3>Summary</h3><p className="profile-summary">{candidate.summary}</p></section>}
                <section className="profile-section">
                  <h3>Search match</h3>
                  {candidate.matched_requirements.filter((item) => item.matched).map((item, index) => (
                    <div className="profile-match" key={`${item.requirement}-${index}`}>
                      <span>{item.requirement}</span>
                      <p>{item.evidence?.find((proof) => proof.text)?.text ?? item.candidate_value ?? "Matched candidate profile"}</p>
                    </div>
                  ))}
                </section>
              </div>

              <div className="profile-tab-panel" data-tab="experience" hidden={profileTab !== "experience"}>
                <section className="profile-section">
                  <h3>Experience{candidate.total_experience_months !== undefined ? ` · ${formatMonths(candidate.total_experience_months)} total` : ""}</h3>
                  {candidate.experience_timeline.length ? candidate.experience_timeline.map((item, index) => (
                    <article className="profile-entry" key={`${item.role}-${item.company}-${index}`}>
                      <strong>{item.role ?? "Role not listed"}</strong>
                      <p>{item.company ?? "Company not listed"}</p>
                      <span>{formatTimelineDate(item.start_date)} – {item.is_current ? "Present" : formatTimelineDate(item.end_date)}</span>
                      {item.description && <p className="profile-entry-description">{item.description}</p>}
                    </article>
                  )) : <p className="profile-muted">No experience history available.</p>}
                </section>
              </div>

              <div className="profile-tab-panel" data-tab="projects" hidden={profileTab !== "projects"}>
                <section className="profile-section">
                  <h3>Projects</h3>
                  {candidate.projects.length ? candidate.projects.map((project, index) => (
                    <article className="profile-entry" key={`${project.title}-${index}`}>
                      <strong>{project.title}</strong>
                      {project.description && <p className="profile-entry-description">{project.description}</p>}
                      {project.skills && project.skills.length > 0 && <div className="profile-entry-skills">{project.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
                      {project.url && normalizeExternalUrl(project.url) && <a className="profile-project-link" href={normalizeExternalUrl(project.url) ?? undefined} target="_blank" rel="noopener noreferrer">Open project ↗</a>}
                    </article>
                  )) : <p className="profile-muted">No project details available.</p>}
                </section>
              </div>

              <div className="profile-tab-panel" data-tab="education" hidden={profileTab !== "education"}>
                <section className="profile-section">
                  <h3>Education</h3>
                  {candidate.education.length ? candidate.education.map((item, index) => (
                    <article className="profile-entry" key={`${item.institution}-${item.degree}-${index}`}>
                      <strong>{item.degree ?? item.field_of_study ?? "Education"}</strong>
                      <p>{item.institution ?? "Institution not listed"}</p>
                      {(item.start_date || item.end_date) && <span>{formatTimelineDate(item.start_date)} – {formatTimelineDate(item.end_date)}</span>}
                    </article>
                  )) : <p className="profile-muted">No education history available.</p>}
                </section>
              </div>

              <div className="profile-tab-panel" data-tab="skills" hidden={profileTab !== "skills"}>
                <section className="profile-section">
                  <h3>Skills</h3>
                  {candidate.profile_skills.length ? <div className="profile-skill-list">{candidate.profile_skills.map((skill) => <span key={skill}>{skill}</span>)}</div> : <p className="profile-muted">No skills available.</p>}
                </section>
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
