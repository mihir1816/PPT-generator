import { type ReactNode } from "react";
import { Check } from "lucide-react";

export type StageState = "done" | "active" | "pending" | "error";

export interface Stage {
  id: string;
  title: string;
  detail: string;
  state: StageState;
  content?: ReactNode;
}

function StageIcon({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <div className="w-7 h-7 rounded-full bg-success flex items-center justify-center flex-shrink-0">
        <Check size={15} className="text-white" strokeWidth={3} aria-hidden />
      </div>
    );
  }
  if (state === "active") {
    return (
      <div
        className="w-7 h-7 rounded-full border-[3px] border-line border-t-accent
          animate-spin flex-shrink-0"
        role="status"
        aria-label="In progress"
      />
    );
  }
  if (state === "error") {
    return (
      <div className="w-7 h-7 rounded-full bg-red-500 flex items-center justify-center flex-shrink-0">
        <span className="text-white text-xs font-bold">!</span>
      </div>
    );
  }
  return (
    <div className="w-7 h-7 rounded-full border-2 border-line flex-shrink-0" />
  );
}

export function ProgressStepper({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex flex-col">
      {stages.map((stage, i) => {
        const isLast = i === stages.length - 1;
        const titleColor =
          stage.state === "active"
            ? "text-accent-ink"
            : stage.state === "done"
            ? "text-ink"
            : stage.state === "error"
            ? "text-red-500"
            : "text-ink3";
        return (
          <li key={stage.id} className="flex gap-4">
            <div className="flex flex-col items-center">
              <StageIcon state={stage.state} />
              {!isLast && (
                <div
                  className={`w-0.5 flex-1 mt-1 min-h-[18px] ${
                    stage.state === "done" ? "bg-success" : "bg-line"
                  }`}
                  aria-hidden
                />
              )}
            </div>
            <div className={`flex-1 ${isLast ? "" : "pb-6"}`}>
              <div className="flex items-center justify-between gap-3">
                <span className={`font-heading font-bold text-[15px] ${titleColor}`}>
                  {stage.title}
                </span>
                <span className="text-xs text-ink3 whitespace-nowrap">
                  {stage.detail}
                </span>
              </div>
              {stage.content && <div className="mt-2">{stage.content}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
