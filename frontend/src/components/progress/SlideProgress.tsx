import { FileText } from "lucide-react";

export interface SlideThumb {
  title: string;
  tone: "accent" | "success" | "warn";
}

const toneBg: Record<SlideThumb["tone"], string> = {
  accent: "bg-accent-bg",
  success: "bg-success-bg",
  warn: "bg-warn-bg",
};

const TONE_CYCLE: SlideThumb["tone"][] = ["accent", "success", "warn"];

export function SlideProgress({
  completed,
  total,
  slideTitles,
}: {
  completed: number;
  total: number;
  slideTitles: string[];
}) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const thumbs: SlideThumb[] = slideTitles.map((title, i) => ({
    title,
    tone: TONE_CYCLE[i % TONE_CYCLE.length],
  }));

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-2.5">
        <div
          className="flex-1 h-2 rounded-full bg-line overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full bg-accent rounded-full transition-[width] duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs font-bold text-ink2 whitespace-nowrap">
          {completed} / {total} slides
        </span>
      </div>
      <div className="flex gap-2.5 overflow-x-auto pb-1">
        {thumbs.map((t, i) => (
          <div
            key={i}
            className="w-[118px] flex-shrink-0 rounded-xl overflow-hidden border border-line bg-surface2 shadow-[0_2px_0_var(--color-line)]"
          >
            <div className={`h-[64px] flex items-center justify-center ${toneBg[t.tone]}`}>
              <FileText size={16} className="text-ink3" aria-hidden />
            </div>
            <div className="px-2.5 py-1.5 text-[10.5px] font-semibold text-ink2 truncate">
              {t.title}
            </div>
          </div>
        ))}
        {completed < total && (
          <div className="w-[118px] h-[92px] flex-shrink-0 rounded-xl border-2 border-dashed border-line flex items-center justify-center">
            <div className="w-4 h-4 rounded-full border-2 border-line border-t-accent animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
