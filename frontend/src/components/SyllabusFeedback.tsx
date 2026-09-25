import { useState } from "react";

interface SyllabusFeedbackProps {
  onSubmit: (feedback: string) => void;
  disabled?: boolean;
  loading?: boolean;
}

export default function SyllabusFeedback({
  onSubmit,
  disabled,
  loading,
}: SyllabusFeedbackProps) {
  const [feedback, setFeedback] = useState("");

  const handleSubmit = () => {
    if (feedback.trim()) {
      onSubmit(feedback.trim());
      setFeedback("");
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <label className="mb-2 block text-sm font-medium text-gray-700">
        Feedback
      </label>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder='e.g. "Remove topic 3, expand topic 2 with more examples..."'
        rows={3}
        disabled={disabled || loading}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50"
      />
      <div className="mt-2 flex justify-end">
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !feedback.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Updating..." : "Send Feedback"}
        </button>
      </div>
    </div>
  );
}
