import { Sun, Moon } from "lucide-react";
import { useTheme } from "../../lib/useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${isLight ? "dark" : "light"} mode`}
      className="flex items-center bg-bg border border-line rounded-pill p-[3px]"
    >
      <span
        className={`p-1.5 rounded-pill flex ${isLight ? "bg-surface" : ""}`}
      >
        <Sun
          size={15}
          className={isLight ? "text-ink" : "text-ink3"}
          aria-hidden
        />
      </span>
      <span
        className={`p-1.5 rounded-pill flex ${!isLight ? "bg-surface" : ""}`}
      >
        <Moon
          size={15}
          className={!isLight ? "text-ink" : "text-ink3"}
          aria-hidden
        />
      </span>
    </button>
  );
}
