import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2.5 border border-line rounded-2xl px-4 py-3 bg-surface2"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={3}
        className="flex-1 bg-transparent text-sm text-ink placeholder:text-ink3 outline-none disabled:opacity-50 resize-none leading-relaxed max-h-[200px]"
      />
      <button
        type="submit"
        aria-label="Send feedback"
        disabled={!value.trim() || disabled}
        className="w-8 h-8 rounded-full bg-accent disabled:opacity-40 flex items-center justify-center flex-shrink-0 mb-0.5"
      >
        {disabled ? (
          <Loader2 size={15} className="text-white animate-spin" aria-hidden />
        ) : (
          <Send size={15} className="text-white" aria-hidden />
        )}
      </button>
    </form>
  );
}
