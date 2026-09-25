import { useState } from "react";

interface URLInputProps {
  onSubmit: (url: string) => void;
  disabled?: boolean;
}

export default function URLInput({ onSubmit, disabled }: URLInputProps) {
  const [url, setUrl] = useState("");

  const handleSubmit = () => {
    const trimmed = url.trim();
    if (trimmed && (trimmed.startsWith("http://") || trimmed.startsWith("https://"))) {
      onSubmit(trimmed);
      setUrl("");
    }
  };

  return (
    <div className="flex gap-2">
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://example.com/article"
        disabled={disabled}
        className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50"
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !url.trim()}
        className="rounded-md bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
      >
        + Add URL
      </button>
    </div>
  );
}
