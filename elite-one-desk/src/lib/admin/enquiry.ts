export const ENQUIRY_STATUSES = [
  "new",
  "contacted",
  "in_progress",
  "waiting_customer",
  "completed",
  "closed",
  "spam",
] as const;

export type EnquiryStatus = (typeof ENQUIRY_STATUSES)[number];

export const STATUS_LABEL: Record<EnquiryStatus, string> = {
  new: "New",
  contacted: "Contacted",
  in_progress: "In progress",
  waiting_customer: "Waiting for customer",
  completed: "Completed",
  closed: "Closed",
  spam: "Spam",
};

export const STATUS_TONE: Record<EnquiryStatus, string> = {
  new: "#ffa476",
  contacted: "#7fb2ff",
  in_progress: "#ffd166",
  waiting_customer: "#c9a6ff",
  completed: "#63c98c",
  closed: "#9aa2b5",
  spam: "#ff8a80",
};

export const CONTACT_LABEL: Record<string, string> = {
  phone: "Phone",
  whatsapp: "WhatsApp",
  email: "Email",
};

export const isEnquiryStatus = (value: string): value is EnquiryStatus =>
  (ENQUIRY_STATUSES as readonly string[]).includes(value);
