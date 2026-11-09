export const CONTACT_STATUSES = [
  "To contact",
  "Contacted",
  "Replied",
  "Interviewing",
  "Hired",
  "Not interested",
] as const;

export type ContactStatus = (typeof CONTACT_STATUSES)[number];

export type ContactRecord<T extends { id: number }> = {
  candidate: T;
  status: ContactStatus;
  addedAt: string;
  updatedAt: string;
  contactedAt: string | null;
  sourceQuery: string | null;
};

export function getContactedContacts<T extends { id: number }>(
  contacts: ContactRecord<T>[],
): ContactRecord<T>[] {
  return contacts.filter((contact) => contact.status !== "To contact");
}

type ContactStorageResult<T> = {
  value: T | null;
  error: string | null;
};

const CONTACT_STORAGE_KEY = "geniehire:contacts:v1";

function isContactStatus(value: unknown): value is ContactStatus {
  return CONTACT_STATUSES.some((status) => status === value);
}

export function loadContacts<T extends { id: number }>(): ContactStorageResult<ContactRecord<T>[]> {
  try {
    const stored = window.localStorage.getItem(CONTACT_STORAGE_KEY);
    if (!stored) return { value: [], error: null };
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) {
      return { value: null, error: "Saved contacts could not be read because the stored data is invalid." };
    }

    const contacts = parsed.filter((item): item is ContactRecord<T> => {
      if (!item || typeof item !== "object") return false;
      const record = item as Record<string, unknown>;
      const candidate = record.candidate;
      return Boolean(
        candidate &&
        typeof candidate === "object" &&
        typeof (candidate as Record<string, unknown>).id === "number" &&
        isContactStatus(record.status) &&
        typeof record.addedAt === "string" &&
        typeof record.updatedAt === "string" &&
        (record.contactedAt === null || typeof record.contactedAt === "string") &&
        (record.sourceQuery === null || typeof record.sourceQuery === "string")
      );
    });

    if (contacts.length !== parsed.length) {
      return { value: contacts, error: "Some saved contact records were invalid and could not be restored." };
    }
    return { value: contacts, error: null };
  } catch {
    return { value: null, error: "Saved contacts could not be loaded from this browser." };
  }
}

export function saveContacts<T extends { id: number }>(
  contacts: ContactRecord<T>[],
): ContactStorageResult<true> {
  try {
    window.localStorage.setItem(CONTACT_STORAGE_KEY, JSON.stringify(contacts));
    return { value: true, error: null };
  } catch {
    return { value: null, error: "Contacts could not be saved. Check this browser's storage settings." };
  }
}
