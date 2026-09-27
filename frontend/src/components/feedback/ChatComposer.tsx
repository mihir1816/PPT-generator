import { useState, type FormEvent } from "react";
import { Send } from "lucide-react";

export function ChatComposer({
  placeholder,
  onSend,
  disabled,
}: {
  placeholder: string;
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 border border-line rounded-pill px-3.5 py-2 bg-surface2"
    >
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 bg-transparent text-[13px] text-ink placeholder:text-ink3 outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        aria-label="Send feedback"
        disabled={!value.trim() || disabled}
        className="w-7 h-7 rounded-full bg-accent disabled:opacity-40 flex items-center justify-center flex-shrink-0"
      >
        <Send size={14} className="text-white" aria-hidden />
      </button>
    </form>
  );
}
