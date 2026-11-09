export type CandidateMatchRequirement = {
  matched: boolean;
  status?: string;
};

export type CandidateDisplayMatchStatus = "MATCH" | "PARTIAL_MATCH";

export function getCandidateDisplayMatchStatus(
  status: string | undefined,
  requirements: CandidateMatchRequirement[],
): CandidateDisplayMatchStatus {
  const normalizedStatus = status?.trim().toLocaleUpperCase();
  if (
    normalizedStatus === "PARTIAL_MATCH" ||
    normalizedStatus === "NO_MATCH" ||
    requirements.some((requirement) =>
      requirement.status?.trim().toLocaleUpperCase() === "PARTIAL_MATCH" ||
      requirement.status?.trim().toLocaleUpperCase() === "NO_MATCH" ||
      !requirement.matched
    )
  ) {
    return "PARTIAL_MATCH";
  }
  if (normalizedStatus === "MATCH") return "MATCH";
  if (
    requirements.length > 0 &&
    requirements.every((requirement) =>
      requirement.matched &&
      requirement.status?.trim().toLocaleUpperCase() !== "PARTIAL_MATCH" &&
      requirement.status?.trim().toLocaleUpperCase() !== "NO_MATCH"
    )
  ) {
    return "MATCH";
  }
  return "PARTIAL_MATCH";
}
