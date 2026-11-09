export type MailboxProvider = "gmail" | "outlook" | "imap" | "none";

export type MailboxConnection = {
  isConnected: boolean;
  provider: MailboxProvider;
  email?: string;
  connectedAt?: string;
  doLater?: boolean;
};

export type SequenceStep = {
  id: string;
  stepNumber: number;
  delayDays: number;
  subject: string;
  body: string;
};

export type Sequence = {
  id: string;
  name: string;
  description?: string;
  steps: SequenceStep[];
  createdAt: string;
};

export type CandidateEnrollment = {
  candidateId: number;
  sequenceId: string;
  currentStep: number;
  enrolledAt: string;
  status: "ACTIVE" | "PAUSED" | "REPLIED" | "COMPLETED";
};

const MAILBOX_STORAGE_KEY = "geniehire:mailbox:v1";
const SEQUENCES_STORAGE_KEY = "geniehire:sequences:v1";
const ENROLLMENTS_STORAGE_KEY = "geniehire:enrollments:v1";

export const DEFAULT_SEQUENCES: Sequence[] = [
  {
    id: "seq-eng-outbound",
    name: "Engineering Outreach (3 Steps)",
    description: "Multi-touch engineering sequence for top tech candidates",
    createdAt: new Date().toISOString(),
    steps: [
      {
        id: "step-1",
        stepNumber: 1,
        delayDays: 0,
        subject: "Exciting opportunity at our engineering team for {{firstName}}",
        body: "Hi {{firstName}},\n\nI came across your profile and was really impressed by your background in {{topSkill}} at {{company}}.\n\nWe are currently scaling our engineering team for our {{searchQuery}} initiatives and your experience looks like a great match. Would you be open to a quick 15-minute intro chat this week?\n\nBest regards,\nShraddha",
      },
      {
        id: "step-2",
        stepNumber: 2,
        delayDays: 3,
        subject: "Quick follow up / {{firstName}}",
        body: "Hi {{firstName}},\n\nJust wanted to follow up on my previous note. I know you are busy, but I wanted to make sure this didn't slip through the cracks.\n\nOur team is working on cutting-edge problems and we'd love to share more about our roadmap and tech stack with you.\n\nLet me know if you have a few minutes to connect.\n\nBest,\nShraddha",
      },
      {
        id: "step-3",
        stepNumber: 3,
        delayDays: 4,
        subject: "Last check-in regarding our open role",
        body: "Hi {{firstName}},\n\nOne last check-in from my side. If now isn't the right time to explore new opportunities, totally understood! We can stay in touch for the future.\n\nIf you change your mind or want to hear more details, feel free to drop me a note.\n\nWishing you all the best,\nShraddha",
      },
    ],
  },
  {
    id: "seq-quick-pitch",
    name: "Quick Pitch (2 Steps)",
    description: "Short two-step outreach for passive candidates",
    createdAt: new Date().toISOString(),
    steps: [
      {
        id: "step-1",
        stepNumber: 1,
        delayDays: 0,
        subject: "Intro: {{role}} opportunity",
        body: "Hi {{firstName}},\n\nSaw your impressive work at {{company}}. We're hiring for a {{role}} and think you'd be a fantastic fit.\n\nWould you have 10 minutes to chat?\n\nBest,\nShraddha",
      },
      {
        id: "step-2",
        stepNumber: 2,
        delayDays: 3,
        subject: "Re: {{role}} opportunity",
        body: "Hi {{firstName}},\n\nFollowing up briefly in case this got buried. Would love to connect whenever you have a moment!\n\nBest,\nShraddha",
      },
    ],
  },
];

export function loadMailboxConnection(): MailboxConnection {
  try {
    const raw = window.localStorage.getItem(MAILBOX_STORAGE_KEY);
    if (!raw) return { isConnected: false, provider: "none", doLater: false };
    return JSON.parse(raw);
  } catch {
    return { isConnected: false, provider: "none", doLater: false };
  }
}

export function saveMailboxConnection(config: MailboxConnection): void {
  try {
    window.localStorage.setItem(MAILBOX_STORAGE_KEY, JSON.stringify(config));
  } catch (error) {
    console.error("Failed to save mailbox connection", error);
  }
}

export function loadSequences(): Sequence[] {
  try {
    const raw = window.localStorage.getItem(SEQUENCES_STORAGE_KEY);
    if (!raw) {
      saveSequences(DEFAULT_SEQUENCES);
      return DEFAULT_SEQUENCES;
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : DEFAULT_SEQUENCES;
  } catch {
    return DEFAULT_SEQUENCES;
  }
}

export function saveSequences(sequences: Sequence[]): void {
  try {
    window.localStorage.setItem(SEQUENCES_STORAGE_KEY, JSON.stringify(sequences));
  } catch (error) {
    console.error("Failed to save sequences", error);
  }
}

export function loadEnrollments(): Record<number, CandidateEnrollment> {
  try {
    const raw = window.localStorage.getItem(ENROLLMENTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

export function saveEnrollments(enrollments: Record<number, CandidateEnrollment>): void {
  try {
    window.localStorage.setItem(ENROLLMENTS_STORAGE_KEY, JSON.stringify(enrollments));
  } catch (error) {
    console.error("Failed to save sequence enrollments", error);
  }
}

export function enrollCandidatesInSequence(
  candidateIds: number[],
  sequenceId: string,
): Record<number, CandidateEnrollment> {
  const current = loadEnrollments();
  const now = new Date().toISOString();

  for (const id of candidateIds) {
    current[id] = {
      candidateId: id,
      sequenceId,
      currentStep: 1,
      enrolledAt: now,
      status: "ACTIVE",
    };
  }

  saveEnrollments(current);
  return { ...current };
}

export function removeCandidateEnrollment(candidateId: number): Record<number, CandidateEnrollment> {
  const current = loadEnrollments();
  delete current[candidateId];
  saveEnrollments(current);
  return { ...current };
}

export function interpolateTemplate(
  template: string,
  variables: {
    firstName?: string;
    company?: string;
    role?: string;
    topSkill?: string;
    searchQuery?: string;
  },
): string {
  let result = template;
  result = result.replaceAll("{{firstName}}", variables.firstName || "there");
  result = result.replaceAll("{{company}}", variables.company || "your company");
  result = result.replaceAll("{{role}}", variables.role || "this role");
  result = result.replaceAll("{{topSkill}}", variables.topSkill || "your skills");
  result = result.replaceAll("{{searchQuery}}", variables.searchQuery || "our team");
  return result;
}
