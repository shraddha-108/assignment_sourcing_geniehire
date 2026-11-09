import type { Dispatch, SetStateAction } from "react";
import { BANDS, rangeFromSelection, selectionFromRange } from "../features/filters/filterExperience";
import type { LocationSuggestion, SelectedLocation, SeniorityBand } from "../types/candidate";

type QueryFilterField = "roles" | "skills" | "companies" | "domains";
type QueryFilterChip = { key: string; label: string };

type FilterDialogState = {
  open: boolean;
  loading: boolean;
  hasActiveFilters: boolean;
  hasPendingFilters: boolean;
  queryFilterChips: QueryFilterChip[];
  includedDomainCount: number;
  roleFilterSearch: string;
  selectedRoleFilters: string[];
  skillFilterSearch: string;
  selectedSkillFilters: string[];
  selectedSeniorityFilters: SeniorityBand[];
  locationFilterSearch: string;
  locationSuggestions: LocationSuggestion[];
  locationSuggestionsLoading: boolean;
  locationAutocompleteError: string | null;
  selectedLocationFilters: SelectedLocation[];
  selectedMinExperience: string;
  selectedMaxExperience: string;
  companyFilterSearch: string;
  selectedCompanyFilters: string[];
  selectedDomainFilters: string[];
};

type FilterDialogSetters = {
  setRoleFilterSearch: Dispatch<SetStateAction<string>>;
  setSelectedRoleFilters: Dispatch<SetStateAction<string[]>>;
  setSkillFilterSearch: Dispatch<SetStateAction<string>>;
  setSelectedSkillFilters: Dispatch<SetStateAction<string[]>>;
  setSelectedSeniorityFilters: Dispatch<SetStateAction<SeniorityBand[]>>;
  setLocationFilterSearch: Dispatch<SetStateAction<string>>;
  setLocationSuggestions: Dispatch<SetStateAction<LocationSuggestion[]>>;
  setSelectedLocationFilters: Dispatch<SetStateAction<SelectedLocation[]>>;
  setSelectedMinExperience: Dispatch<SetStateAction<string>>;
  setSelectedMaxExperience: Dispatch<SetStateAction<string>>;
  setCompanyFilterSearch: Dispatch<SetStateAction<string>>;
  setSelectedCompanyFilters: Dispatch<SetStateAction<string[]>>;
  setSelectedDomainFilters: Dispatch<SetStateAction<string[]>>;
};

type FilterDialogActions = {
  setters: FilterDialogSetters;
  closeFilterPanel: (discardChanges?: boolean) => void;
  clearAllFilters: () => void;
  applyFilters: () => void | Promise<void>;
  selectGeoapifyLocation: (suggestion: LocationSuggestion) => void;
  queryAlreadyIncludes: (field: QueryFilterField, value: string) => boolean;
  queryAlreadyIncludesLocationText: (value: string) => boolean;
  queryAlreadyIncludesLocationSuggestion: (suggestion: LocationSuggestion) => boolean;
};

type FilterDialogProps = { state: FilterDialogState; actions: FilterDialogActions };

const DOMAIN_OPTIONS = ["TECHNICAL", "SALES", "MARKETING", "HR", "FINANCE", "OPERATIONS", "CUSTOMER_SUCCESS", "PRODUCT", "GENERAL"];

export function FilterDialog({ state, actions }: FilterDialogProps) {
  const {
    open: filterPanelOpen, loading: filterLoading, hasActiveFilters, hasPendingFilters, queryFilterChips, includedDomainCount,
    roleFilterSearch, selectedRoleFilters, skillFilterSearch, selectedSkillFilters, selectedSeniorityFilters,
    locationFilterSearch, locationSuggestions, locationSuggestionsLoading, locationAutocompleteError, selectedLocationFilters,
    selectedMinExperience, selectedMaxExperience, companyFilterSearch, selectedCompanyFilters, selectedDomainFilters,
  } = state;
  const {
    setRoleFilterSearch, setSelectedRoleFilters, setSkillFilterSearch, setSelectedSkillFilters, setSelectedSeniorityFilters,
    setLocationFilterSearch, setLocationSuggestions, setSelectedLocationFilters, setSelectedMinExperience, setSelectedMaxExperience,
    setCompanyFilterSearch, setSelectedCompanyFilters, setSelectedDomainFilters,
  } = actions.setters;
  const { closeFilterPanel, clearAllFilters, applyFilters: handleApplyFilters, selectGeoapifyLocation, queryAlreadyIncludes,
    queryAlreadyIncludesLocationText, queryAlreadyIncludesLocationSuggestion } = actions;
  return (
    <>
      {filterPanelOpen && (
                    <div
                      role="presentation"
                      onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeFilterPanel(true);
                      }}
                      style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1000,
                        background: "rgba(20, 22, 35, 0.30)",
                        backdropFilter: "blur(2px)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "24px",
                        boxSizing: "border-box",
                      }}
                    >
                      <aside
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="filter-panel-title"
                        onMouseDown={(event) => event.stopPropagation()}
                        className="result-filter-panel"
                        style={{
                          width: "min(520px, 94vw)",
                          maxHeight: "min(720px, 88vh)",
                          background: "#ffffff",
                          border: "1px solid #e1e2ec",
                          borderRadius: "18px",
                          boxShadow: "0 24px 70px rgba(20, 22, 35, 0.22)",
                          overflow: "hidden",
                          display: "flex",
                          flexDirection: "column",
                          boxSizing: "border-box",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            justifyContent: "space-between",
                            gap: "16px",
                            padding: "22px 24px 18px",
                            borderBottom: "1px solid #ececf2",
                            background: "#ffffff",
                            flexShrink: 0,
                          }}
                        >
                          <div>
                            <h2 id="filter-panel-title" style={{ margin: 0, fontSize: "20px", fontWeight: 800, color: "#202333" }}>
                              Filters
                            </h2>
                            <p style={{ margin: "6px 0 0", fontSize: "12px", lineHeight: 1.5, color: "#777b8e" }}>
                              Criteria from your original query are already active. Add filters below to narrow the results further.
                            </p>
                          </div>
                          <button
                            type="button"
                            aria-label="Close filters"
                            onClick={() => closeFilterPanel(true)}
                            style={{
                              width: "36px",
                              height: "36px",
                              flexShrink: 0,
                              border: "1px solid #e1e2ec",
                              borderRadius: "10px",
                              background: "#f7f7fa",
                              color: "#4d5061",
                              fontSize: "21px",
                              lineHeight: 1,
                              cursor: "pointer",
                            }}
                          >
                            ×
                          </button>
                        </div>

                        <div
                          style={{
                            padding: "22px 24px 8px",
                            overflowY: "auto",
                            flex: 1,
                            minHeight: 0,
                          }}
                        >
                          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                            {queryFilterChips.length > 0 && (
                              <section
                                aria-label="Filters already included from your query"
                                style={{
                                  padding: "13px 14px",
                                  border: "1px solid #e5e2fb",
                                  borderRadius: "11px",
                                  background: "#f8f7ff",
                                }}
                              >
                                <div style={{ color: "#34304f", fontSize: "12px", fontWeight: 750 }}>
                                  Already included from your query
                                </div>
                                <p style={{ margin: "4px 0 10px", color: "#77748e", fontSize: "11px", lineHeight: 1.45 }}>
                                  These criteria are already applied and won’t be added again. Edit the search query to change them.
                                </p>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                                  {queryFilterChips.map((item) => (
                                    <span
                                      key={item.key}
                                      style={{
                                        padding: "5px 8px",
                                        border: "1px solid #e2def8",
                                        borderRadius: "7px",
                                        background: "#fff",
                                        color: "#554d85",
                                        fontSize: "11px",
                                        fontWeight: 600,
                                      }}
                                    >
                                      {item.label}
                                    </span>
                                  ))}
                                </div>
                              </section>
                            )}
                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Role</legend>
                              <div className="manual-role-filter">
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={roleFilterSearch}
                                  onChange={(event) => setRoleFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      const role = roleFilterSearch.trim();
                                      if (role && !queryAlreadyIncludes("roles", role) && !selectedRoleFilters.some((item) => item.toLocaleLowerCase() === role.toLocaleLowerCase())) {
                                        setSelectedRoleFilters((current) => [...current, role]);
                                        setRoleFilterSearch("");
                                      }
                                    }
                                    if (event.key === "Backspace" && !roleFilterSearch.trim() && selectedRoleFilters.length > 0) {
                                      setSelectedRoleFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Type a role and press Enter"
                                  aria-label="Add a role filter"
                                />
                                {queryAlreadyIncludes("roles", roleFilterSearch) && (
                                  <p className="filter-group-note">Already included in the original query.</p>
                                )}
                                {selectedRoleFilters.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                    {selectedRoleFilters.map((role) => (
                                      <span key={role} style={{ display: "inline-flex", alignItems: "center", gap: "7px", minHeight: "28px", padding: "4px 7px 4px 10px", border: "1px solid #d9dbe7", borderRadius: "8px", background: "#f7f7fb", color: "#4b4e60", fontSize: "12px", fontWeight: 600, lineHeight: 1 }}>
                                        <span>{role}</span>
                                        <button type="button" aria-label={`Remove ${role}`} onClick={() => setSelectedRoleFilters((current) => current.filter((item) => item !== role))} style={{ width: "18px", height: "18px", padding: 0, border: 0, background: "transparent", color: "#5f6272", cursor: "pointer", fontSize: "15px" }}>×</button>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Skills</legend>
                              <div className="manual-skill-filter">
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={skillFilterSearch}
                                  onChange={(event) => setSkillFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      const skill = skillFilterSearch.trim();
                                      if (skill && !queryAlreadyIncludes("skills", skill) && !selectedSkillFilters.some((item) => item.toLocaleLowerCase() === skill.toLocaleLowerCase())) {
                                        setSelectedSkillFilters((current) => [...current, skill]);
                                        setSkillFilterSearch("");
                                      }
                                    }
                                    if (event.key === "Backspace" && !skillFilterSearch.trim() && selectedSkillFilters.length > 0) {
                                      setSelectedSkillFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Type a skill and press Enter"
                                  aria-label="Add a skill filter"
                                />
                                {queryAlreadyIncludes("skills", skillFilterSearch) && (
                                  <p className="filter-group-note">Already included in the original query.</p>
                                )}
                                {selectedSkillFilters.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                    {selectedSkillFilters.map((skill) => (
                                      <span key={skill} style={{ display: "inline-flex", alignItems: "center", gap: "7px", minHeight: "28px", padding: "4px 7px 4px 10px", border: "1px solid #d9dbe7", borderRadius: "8px", background: "#f7f7fb", color: "#4b4e60", fontSize: "12px", fontWeight: 600, lineHeight: 1 }}>
                                        <span>{skill}</span>
                                        <button type="button" aria-label={`Remove ${skill}`} onClick={() => setSelectedSkillFilters((current) => current.filter((item) => item !== skill))} style={{ width: "18px", height: "18px", padding: 0, border: 0, background: "transparent", color: "#5f6272", cursor: "pointer", fontSize: "15px" }}>×</button>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Location</legend>
                              <div style={{ position: "relative" }}>
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={locationFilterSearch}
                                  onChange={(event) => setLocationFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter" && locationSuggestions.length > 0) {
                                      event.preventDefault();
                                      if (queryAlreadyIncludesLocationSuggestion(locationSuggestions[0])) {
                                        setLocationFilterSearch("");
                                        setLocationSuggestions([]);
                                      } else {
                                        selectGeoapifyLocation(locationSuggestions[0]);
                                      }
                                    }
                                    if (event.key === "Escape") setLocationSuggestions([]);
                                    if (event.key === "Backspace" && !locationFilterSearch.trim() && selectedLocationFilters.length > 0) {
                                      setSelectedLocationFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Search city or locality"
                                  aria-label="Search for a candidate location"
                                  autoComplete="off"
                                />
                                {queryAlreadyIncludesLocationText(locationFilterSearch) && (
                                  <p className="filter-group-note">Already included in the original query.</p>
                                )}
                                {(locationSuggestionsLoading || locationSuggestions.length > 0 || locationAutocompleteError) && (
                                  <div
                                    role="listbox"
                                    style={{
                                      position: "absolute",
                                      zIndex: 30,
                                      top: "calc(100% + 5px)",
                                      left: 0,
                                      right: 0,
                                      background: "#fff",
                                      border: "1px solid #d9dce8",
                                      borderRadius: "9px",
                                      boxShadow: "0 8px 24px rgba(20, 25, 45, 0.12)",
                                      maxHeight: "220px",
                                      overflowY: "auto",
                                    }}
                                  >
                                    {locationSuggestionsLoading && (
                                      <div style={{ padding: "11px 13px", color: "#73788b", fontSize: "13px" }}>Searching locations…</div>
                                    )}
                                    {locationAutocompleteError && (
                                      <div style={{ padding: "11px 13px", color: "#b42318", fontSize: "12px" }}>{locationAutocompleteError}</div>
                                    )}
                                    {locationSuggestions.map((suggestion, index) => (
                                      <button
                                        type="button"
                                        role="option"
                                        aria-selected="false"
                                        key={`${suggestion.properties?.place_id ?? suggestion.text}-${index}`}
                                        onMouseDown={(event) => event.preventDefault()}
                                        onClick={() => {
                                          if (queryAlreadyIncludesLocationSuggestion(suggestion)) {
                                            setLocationFilterSearch("");
                                            setLocationSuggestions([]);
                                          } else {
                                            selectGeoapifyLocation(suggestion);
                                          }
                                        }}
                                        style={{
                                          display: "block",
                                          width: "100%",
                                          padding: "11px 13px",
                                          border: 0,
                                          borderBottom: "1px solid #f0f1f5",
                                          background: "#fff",
                                          color: "#25283a",
                                          textAlign: "left",
                                          cursor: "pointer",
                                          fontSize: "13px",
                                        }}
                                      >
                                        <span style={{ display: "flex", alignItems: "center", gap: "9px" }}>
                                          <span aria-hidden="true">⌖</span>
                                          <span>{suggestion.text}</span>
                                        </span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                             
                              {selectedLocationFilters.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                  {selectedLocationFilters.map((location) => (
                                    <span className="requirement-pill" key={location.place_id}>
                                      {location.label}
                                      <button type="button" aria-label={`Remove ${location.label}`} onClick={() => setSelectedLocationFilters((current) => current.filter((item) => item.place_id !== location.place_id))} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: "pointer" }}>×</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Experience</legend>
                              <p className="filter-group-note">Filter by total professional experience. The maximum includes that full year (7 means under 8 years).</p>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                                <input className="filter-dropdown-search" type="number" min="0" step="0.5" value={selectedMinExperience} disabled={selectedSeniorityFilters.length > 0 && !rangeFromSelection(selectedSeniorityFilters)} onChange={(event) => {
                                  const value = event.target.value;
                                  setSelectedMinExperience(value);
                                  const minimum = value.trim() ? Number(value) : null;
                                  const maximum = selectedMaxExperience.trim() ? Number(selectedMaxExperience) : null;
                                  setSelectedSeniorityFilters(selectionFromRange(minimum, maximum));
                                }} placeholder="Min years" aria-label="Minimum experience in years" />
                                <input className="filter-dropdown-search" type="number" min="0" step="0.5" value={selectedMaxExperience} disabled={selectedSeniorityFilters.length > 0 && !rangeFromSelection(selectedSeniorityFilters)} onChange={(event) => {
                                  const value = event.target.value;
                                  setSelectedMaxExperience(value);
                                  const minimum = selectedMinExperience.trim() ? Number(selectedMinExperience) : null;
                                  const maximum = value.trim() ? Number(value) : null;
                                  setSelectedSeniorityFilters(selectionFromRange(minimum, maximum));
                                }} placeholder="Max years" aria-label="Maximum experience in years" />
                              </div>
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Seniority</legend>
                              <p className="filter-group-note">Based on total experience</p>
                              {BANDS.map((band) => (
                                <label className="filter-option" key={band.key}>
                                  <input
                                    type="checkbox"
                                    checked={selectedSeniorityFilters.includes(band.key)}
                                    onChange={() => {
                                      const next = selectedSeniorityFilters.includes(band.key)
                                        ? selectedSeniorityFilters.filter((item) => item !== band.key)
                                        : [...selectedSeniorityFilters, band.key];
                                      setSelectedSeniorityFilters(next);
                                      if (next.length === 0) {
                                        setSelectedMinExperience("");
                                        setSelectedMaxExperience("");
                                        return;
                                      }
                                      const range = rangeFromSelection(next);
                                      setSelectedMinExperience(range ? String(range.min) : "");
                                      setSelectedMaxExperience(range?.max == null ? "" : String(range.max));
                                    }}
                                  />
                                  <span>{band.label}{band.max === null ? ` · ${band.min}+ years` : ` · ${band.min}–${band.max} years`}</span>
                                </label>
                              ))}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Company</legend>
                              <div className="company-filter-input">
                                <input
                                  className="filter-dropdown-search"
                                  type="text"
                                  value={companyFilterSearch}
                                  onChange={(event) => setCompanyFilterSearch(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      const company = companyFilterSearch.trim();
                                      if (company && !queryAlreadyIncludes("companies", company) && !selectedCompanyFilters.some((item) => item.toLocaleLowerCase() === company.toLocaleLowerCase())) {
                                        setSelectedCompanyFilters((current) => [...current, company]);
                                        setCompanyFilterSearch("");
                                      }
                                    }
                                    if (event.key === "Backspace" && !companyFilterSearch.trim() && selectedCompanyFilters.length > 0) {
                                      setSelectedCompanyFilters((current) => current.slice(0, -1));
                                    }
                                  }}
                                  placeholder="Type a company"
                                  aria-label="Add a company filter"
                                />
                                <button
                                  type="button"
                                  className="company-filter-add"
                                  disabled={!companyFilterSearch.trim() || queryAlreadyIncludes("companies", companyFilterSearch)}
                                  onClick={() => {
                                    const company = companyFilterSearch.trim();
                                    if (company && !queryAlreadyIncludes("companies", company) && !selectedCompanyFilters.some((item) => item.toLocaleLowerCase() === company.toLocaleLowerCase())) {
                                      setSelectedCompanyFilters((current) => [...current, company]);
                                    }
                                    setCompanyFilterSearch("");
                                  }}
                                >
                                  Add
                                </button>
                              </div>
                              {queryAlreadyIncludes("companies", companyFilterSearch) && (
                                <p className="filter-group-note">Already included in the original query.</p>
                              )}
                              {selectedCompanyFilters.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "7px", marginTop: "8px" }}>
                                  {selectedCompanyFilters.map((company) => (
                                    <span className="requirement-pill" key={company}>
                                      {company}
                                      <button type="button" aria-label={`Remove ${company}`} onClick={() => setSelectedCompanyFilters((current) => current.filter((item) => item !== company))} style={{ marginLeft: "6px", border: 0, background: "transparent", cursor: "pointer" }}>×</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                            </fieldset>

                            <fieldset className="filter-group">
                              <legend style={{ fontWeight: 700, color: "#202333" }}>Domain</legend>
                              <details className="filter-dropdown filter-domain-dropdown">
                                <summary className="filter-dropdown-trigger">
                                  <span>
                                    {includedDomainCount
                                      ? `${includedDomainCount} domain${includedDomainCount === 1 ? "" : "s"} included`
                                      : "Select domains"}
                                  </span>
                                  <span className="filter-dropdown-chevron" aria-hidden="true">⌄</span>
                                </summary>
                                <div className="filter-dropdown-menu filter-domain-options">
                                  {DOMAIN_OPTIONS.map((domain) => (
                                    <label className="filter-option" key={domain}>
                                      <input type="checkbox" checked={selectedDomainFilters.includes(domain) || queryAlreadyIncludes("domains", domain)} disabled={queryAlreadyIncludes("domains", domain)} onChange={() => setSelectedDomainFilters((current) => current.includes(domain) ? current.filter((item) => item !== domain) : [...current, domain])} />
                                      <span>{domain.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase())}</span>
                                      {queryAlreadyIncludes("domains", domain) && <span className="filter-group-note">From query</span>}
                                    </label>
                                  ))}
                                </div>
                              </details>
                            </fieldset>
                          </div>
                        </div>

                        <div
                          style={{
                            padding: "14px 24px 18px",
                            background: "#ffffff",
                            borderTop: "1px solid #ececf2",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "12px",
                            flexShrink: 0,
                          }}
                        >
                          <button
                            type="button"
                            onClick={clearAllFilters}
                            disabled={(!hasActiveFilters && !hasPendingFilters) || filterLoading}
                            style={{
                              border: 0,
                              background: "transparent",
                              color: "#6d28d9",
                              fontSize: "13px",
                              fontWeight: 700,
                              cursor: "pointer",
                              padding: "10px 2px",
                              opacity: (!hasActiveFilters && !hasPendingFilters) || filterLoading ? 0.45 : 1,
                            }}
                          >
                            Clear all
                          </button>

                          <div style={{ display: "flex", gap: "8px" }}>
                            <button
                              type="button"
                              onClick={() => closeFilterPanel(true)}
                              disabled={filterLoading}
                              style={{
                                border: "1px solid #d8d9e4",
                                borderRadius: "9px",
                                background: "#fff",
                                color: "#36394a",
                                padding: "10px 15px",
                                fontSize: "13px",
                                fontWeight: 700,
                                cursor: "pointer",
                              }}
                            >
                              Cancel
                            </button>

                            <button
                              type="button"
                              className="filter-apply-button"
                              disabled={!hasPendingFilters || filterLoading}
                              onClick={() => void handleApplyFilters()}
                              style={{
                                border: "1px solid #171a2b",
                                borderRadius: "9px",
                                background: !hasPendingFilters || filterLoading ? "#e9e9ee" : "#171a2b",
                                color: !hasPendingFilters || filterLoading ? "#9295a4" : "#ffffff",
                                padding: "10px 16px",
                                fontSize: "13px",
                                fontWeight: 800,
                                cursor: !hasPendingFilters || filterLoading ? "not-allowed" : "pointer",
                                boxShadow: !hasPendingFilters || filterLoading ? "none" : "0 4px 12px rgba(23, 26, 43, 0.12)",
                              }}
                            >
                              {filterLoading ? "Applying…" : "Apply filters"}
                            </button>
                          </div>
                        </div>
                      </aside>
                    </div>
                  )}
    </>
  );
}
