import type {
  BackendCandidate,
  Evidence,
  ExperienceTimelineEntry,
  MatchedExperience,
  MatchedRequirement,
} from "../../types/candidate";

export function getInitials(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (parts.length === 0) {
    return "?";
  }

  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function formatMonths(
  months?: number
): string {
  if (
    months === undefined ||
    months === null ||
    Number.isNaN(months)
  ) {
    return "Unknown";
  }

  if (months < 12) {
    return `${months} month${months === 1 ? "" : "s"}`;
  }

  const years = Math.floor(months / 12);
  const remainingMonths = months % 12;

  if (remainingMonths === 0) {
    return `${years} year${years === 1 ? "" : "s"}`;
  }

  return `${years}y ${remainingMonths}m`;
}

export function formatTimelineDate(dateString?: string | null): string {
  if (!dateString) return "Date not listed";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return dateString;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function normalizeExternalUrl(value?: string | null): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;

  const candidate = /^[a-z][a-z\d+.-]*:/i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;
  try {
    const url = new URL(candidate);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export function groupMatchedRequirements(
  matches: MatchedRequirement[]
): MatchedRequirement[] {
  const grouped = new Map<string, MatchedRequirement>();
  for (const match of matches) {
    const key = match.requirement.trim().toLocaleLowerCase().replace(/\s+/g, " ");
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        ...match,
        requirement_types: [match.type.toLowerCase()],
        evidence: [...(match.evidence ?? [])],
      });
      continue;
    }
    existing.requirement_types = [...new Set([
      ...(existing.requirement_types ?? [existing.type.toLowerCase()]),
      match.type.toLowerCase(),
    ])];
    if (match.type.toLowerCase() === "skill") {
      existing.type = "skill";
      existing.candidate_value = match.candidate_value ?? existing.candidate_value;
    }
    existing.matched = existing.matched && match.matched;
    existing.evidence = [...(existing.evidence ?? []), ...(match.evidence ?? [])];
    if (existing.candidate_value == null && match.candidate_value != null) {
      existing.candidate_value = match.candidate_value;
    }
  }
  return [...grouped.values()];
}

export function conciseEvidenceText(text: string, requirement: string): string {
  const sentences = text
    .split(/\r?\n+|(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  if (sentences.length <= 1) return text;

  const terms = requirement.toLowerCase().match(/[a-z0-9+#.]+/g) ?? [];
  const ranked = sentences.map((sentence) => {
    const lower = sentence.toLowerCase();
    const score = terms.filter((term) => lower.includes(term)).length;
    return { sentence, score };
  }).sort((left, right) => right.score - left.score || left.sentence.length - right.sentence.length);
  const best = ranked.find((item) => item.score > 0)?.sentence ?? sentences[0];
  return best.length > 360 ? `${best.slice(0, 357).trimEnd()}…` : best;
}

export function evidenceSectionLabel(evidence: Evidence): string {
  const type = (evidence.section_type || evidence.evidence_type || "").trim().toLowerCase();
  if (type.includes("project")) return "Project";
  if (type.includes("experience") || type.includes("work")) return "Experience";
  if (type.includes("summary") || type.includes("profile")) return "Summary";
  if (type.includes("education")) return "Education";
  if (type.includes("skill")) return "Skills";
  if (evidence.section_title?.trim()) return evidence.section_title.trim();
  return "Resume section";
}

export function normalizeComparableText(value?: string | null): string {
  return (value ?? "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ");
}

export function buildMailtoLink(email: string, subject: string, message: string): string {
  const encodedEmail = encodeURIComponent(email).replaceAll("%40", "@");
  return `mailto:${encodedEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(message)}`;
}

export function getMatchedExperience(
  raw: BackendCandidate,
  experienceTimeline: ExperienceTimelineEntry[],
  matchedRequirements: MatchedRequirement[]
): MatchedExperience | null {
  if (raw.matched_experience) {
    return raw.matched_experience;
  }

  const matched = matchedRequirements.filter(
    (item) => item.matched && item.status !== "NO_MATCH"
  );

  const roleMatch = matched.find(
    (item) =>
      item.type === "role" ||
      item.requirement_types?.includes("role")
  );

  const companyMatch = matched.find(
    (item) =>
      item.type === "company" ||
      item.requirement_types?.includes("company")
  );

  const requestedRole = normalizeComparableText(
    roleMatch?.candidate_value != null
      ? String(roleMatch.candidate_value)
      : roleMatch?.requirement
  );

  const requestedCompany = normalizeComparableText(
    companyMatch?.candidate_value != null
      ? String(companyMatch.candidate_value)
      : companyMatch?.requirement
  );

  if (!requestedRole && !requestedCompany) {
    return null;
  }

  const candidates = experienceTimeline.filter((experience) => {
    const role = normalizeComparableText(experience.role);
    const company = normalizeComparableText(experience.company);

    const roleMatches =
      !requestedRole || role === requestedRole;
    const companyMatches =
      !requestedCompany || company === requestedCompany;

    return roleMatches && companyMatches;
  });

  if (candidates.length === 0) {
    return null;
  }

  const sorted = [...candidates].sort((a, b) => {
    // Prefer the currently held matching experience.
    if (Boolean(a.is_current) !== Boolean(b.is_current)) {
      return a.is_current ? -1 : 1;
    }

    // If both are current/non-current, prefer the most recent start date.
    const aStart = a.start_date
      ? new Date(a.start_date).getTime()
      : Number.NEGATIVE_INFINITY;
    const bStart = b.start_date
      ? new Date(b.start_date).getTime()
      : Number.NEGATIVE_INFINITY;

    return bStart - aStart;
  });

  return sorted[0];
}
