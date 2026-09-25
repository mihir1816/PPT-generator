const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  generating_syllabus: "bg-blue-100 text-blue-700",
  syllabus_review: "bg-yellow-100 text-yellow-700",
  waiting_for_indexing: "bg-orange-100 text-orange-700",
  ready_for_retrieval: "bg-green-100 text-green-700",
  retrieving: "bg-blue-100 text-blue-700",
  retrieval_complete: "bg-green-100 text-green-700",
  generating_outline: "bg-blue-100 text-blue-700",
  outline_ready: "bg-green-100 text-green-700",
  generating_slides: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  generating_syllabus: "Generating Syllabus",
  syllabus_review: "Syllabus Review",
  waiting_for_indexing: "Indexing Documents",
  ready_for_retrieval: "Ready",
  retrieving: "Retrieving",
  retrieval_complete: "Retrieved",
  generating_outline: "Generating Outline",
  outline_ready: "Outline Ready",
  generating_slides: "Generating Slides",
  completed: "Completed",
  failed: "Failed",
};

export default function StatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] || "bg-gray-100 text-gray-700";
  const label = STATUS_LABELS[status] || status.replace(/_/g, " ");
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}
    >
      {label}
    </span>
  );
}
