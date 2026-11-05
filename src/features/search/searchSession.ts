export type SavedLocation = {
  place_id: string;
  label: string;
  city: string | null;
  state: string | null;
  country: string | null;
};

export type SavedFilters = {
  roles: string[];
  skills: string[];
  seniority: string[];
  locations: SavedLocation[];
  companies: string[];
  domains: string[];
  minExperience: number | null;
  maxExperience: number | null;
};

export type SavedSearch = {
  query: string;
  filters: SavedFilters;
};

const STORAGE_KEY = "geniehire:last-search";

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isSavedLocation(value: unknown): value is SavedLocation {
  if (!value || typeof value !== "object") return false;
  const location = value as Record<string, unknown>;
  return (
    typeof location.place_id === "string" &&
    typeof location.label === "string" &&
    (typeof location.city === "string" || location.city === null) &&
    (typeof location.state === "string" || location.state === null) &&
    (typeof location.country === "string" || location.country === null)
  );
}

function isSavedSearch(value: unknown): value is SavedSearch {
  if (!value || typeof value !== "object") return false;
  const saved = value as Record<string, unknown>;
  if (typeof saved.query !== "string" || !saved.filters || typeof saved.filters !== "object") {
    return false;
  }
  const filters = saved.filters as Record<string, unknown>;
  return (
    isStringArray(filters.roles) &&
    isStringArray(filters.skills) &&
    isStringArray(filters.seniority) &&
    Array.isArray(filters.locations) &&
    filters.locations.every(isSavedLocation) &&
    isStringArray(filters.companies) &&
    isStringArray(filters.domains) &&
    (typeof filters.minExperience === "number" || filters.minExperience === null) &&
    (typeof filters.maxExperience === "number" || filters.maxExperience === null)
  );
}

export function saveSearch(search: SavedSearch): true | null {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(search));
    return true;
  } catch {
    return null;
  }
}

export function loadSearch(): SavedSearch | null {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (!saved) return null;
    const parsed: unknown = JSON.parse(saved);
    return isSavedSearch(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function clearSearch(): true | null {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
    return true;
  } catch {
    return null;
  }
}

export function hasAnyFilter(filters: SavedFilters): boolean {
  return Boolean(
    filters.roles.length ||
    filters.skills.length ||
    filters.seniority.length ||
    filters.locations.length ||
    filters.companies.length ||
    filters.domains.length ||
    filters.minExperience !== null ||
    filters.maxExperience !== null
  );
}
