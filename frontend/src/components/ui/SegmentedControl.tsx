interface SegmentedControlProps {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function SegmentedControl({
  label,
  options,
  value,
  onChange,
  disabled,
}: SegmentedControlProps) {
  return (
    <div>
      <div className="text-[12.5px] font-bold text-ink2 font-body mb-2">
        {label}
      </div>
      <div className="flex gap-2" role="group" aria-label={label}>
        {options.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onChange(opt.value)}
              className={`px-4 py-2 rounded-pill text-[13px] font-bold font-body border transition-colors disabled:opacity-50
                ${
                  active
                    ? "bg-accent text-white border-accent"
                    : "bg-surface text-ink2 border-line hover:bg-accent-bg/30"
                }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
