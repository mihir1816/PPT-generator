import { Badge } from "./Badge";

type Tone = "accent" | "success" | "warn" | "neutral";

const STATUS_TONE: Record<string, Tone> = {
  pending: "neutral",
  generating_syllabus: "accent",
  syllabus_review: "warn",
  waiting_for_indexing: "warn",
  ready_for_retrieval: "success",
  retrieving: "accent",
  retrieval_complete: "success",
  generating_outline: "accent",
  outline_ready: "success",
  generating_slides: "accent",
  completed: "success",
  failed: "warn",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  generating_syllabus: "Generating",
  syllabus_review: "Review",
  waiting_for_indexing: "Indexing",
  ready_for_retrieval: "Ready",
  retrieving: "Retrieving",
  retrieval_complete: "Retrieved",
  generating_outline: "Outlining",
  outline_ready: "Outlined",
  generating_slides: "Generating",
  completed: "Ready",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] || "neutral";
  const label = STATUS_LABELS[status] || status.replace(/_/g, " ");
  return <Badge tone={tone}>{label}</Badge>;
}
