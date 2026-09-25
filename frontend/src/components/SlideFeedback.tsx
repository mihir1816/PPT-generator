import { useState } from "react";

interface SlideFeedbackProps {
  onSubmit: (feedback: string) => void;
  onUndo: () => void;
  disabled?: boolean;
  loading?: boolean;
  canUndo?: boolean;
}

export default function SlideFeedback({
  onSubmit,
  onUndo,
  disabled,
  loading,
  canUndo,
}: SlideFeedbackProps) {
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
        Slide Feedback
      </label>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder='e.g. "Expand slide 3, remove slide 5, add more examples to slide 2..."'
        rows={3}
        disabled={disabled || loading}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50"
      />
      <div className="mt-2 flex items-center justify-end gap-2">
        {canUndo && (
          <button
            onClick={onUndo}
            disabled={loading}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Undo Last
          </button>
        )}
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !feedback.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Processing..." : "Send Feedback"}
        </button>
      </div>
    </div>
  );
}
