import type { TeacherPreferences } from "../types";

interface PreferencesFormProps {
  preferences: TeacherPreferences;
  onChange: (prefs: TeacherPreferences) => void;
  description: string;
  onDescriptionChange: (v: string) => void;
  outline: string;
  onOutlineChange: (v: string) => void;
  showOutline: boolean;
  onToggleOutline: (v: boolean) => void;
  disabled?: boolean;
}

function ToggleGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <div className="flex gap-1">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              value === opt.value
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            } disabled:opacity-50`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function PreferencesForm({
  preferences,
  onChange,
  description,
  onDescriptionChange,
  outline,
  onOutlineChange,
  showOutline,
  onToggleOutline,
  disabled,
}: PreferencesFormProps) {
  const update = (partial: Partial<TeacherPreferences>) =>
    onChange({ ...preferences, ...partial });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ToggleGroup
          label="Tone"
          value={preferences.tone}
          options={[
            { value: "formal", label: "Formal" },
            { value: "creative", label: "Creative" },
          ]}
          onChange={(v) => update({ tone: v })}
          disabled={disabled}
        />
        <ToggleGroup
          label="Content"
          value={preferences.content_mode}
          options={[
            { value: "grounded", label: "Grounded" },
            { value: "mixed", label: "Mixed" },
          ]}
          onChange={(v) => update({ content_mode: v })}
          disabled={disabled}
        />
        <ToggleGroup
          label="Level"
          value={preferences.audience_level}
          options={[
            { value: "beginner", label: "Beginner" },
            { value: "intermediate", label: "Intermediate" },
            { value: "advanced", label: "Advanced" },
          ]}
          onChange={(v) => update({ audience_level: v })}
          disabled={disabled}
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Description
        </label>
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder="Describe what this presentation should cover..."
          rows={3}
          disabled={disabled}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50"
        />
      </div>

      <div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Outline</label>
          <button
            type="button"
            onClick={() => onToggleOutline(!showOutline)}
            disabled={disabled}
            className="text-xs text-blue-600 hover:underline disabled:opacity-50"
          >
            {showOutline ? "Remove outline" : "Provide outline"}
          </button>
        </div>
        {showOutline && (
          <textarea
            value={outline}
            onChange={(e) => onOutlineChange(e.target.value)}
            placeholder="Optional: provide a rough outline for the presentation..."
            rows={4}
            disabled={disabled}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50"
          />
        )}
      </div>
    </div>
  );
}
