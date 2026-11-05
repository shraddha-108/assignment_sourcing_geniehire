type SearchHeaderProps = {
  status: "checking" | "connected" | "offline";
};

export function SearchHeader({ status }: SearchHeaderProps) {
  return (
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            G
          </div>

          <div>
            <div className="brand-name">
              GenieHire
            </div>

            <div className="brand-subtitle">
              Recruiter Intelligence
            </div>
          </div>
        </div>

        <div className={`topbar-status is-${status}`} role="status" aria-live="polite">
          <span className="status-dot" />
          {status === "checking" ? "Checking database…" : status === "connected" ? "Talent database connected" : "Database unavailable"}
        </div>
      </header>
  );
}
