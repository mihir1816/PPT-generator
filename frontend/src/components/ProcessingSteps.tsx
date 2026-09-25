type StepState = "pending" | "active" | "done" | "error";

interface Step {
  label: string;
  state: StepState;
}

interface ProcessingStepsProps {
  steps: Step[];
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return <span className="text-green-600">&#10003;</span>;
  }
  if (state === "active") {
    return (
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
    );
  }
  if (state === "error") {
    return <span className="text-red-600">&#10007;</span>;
  }
  return <span className="text-gray-300">&#9675;</span>;
}

export default function ProcessingSteps({ steps }: ProcessingStepsProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h4 className="mb-3 text-sm font-medium text-gray-700">Processing</h4>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-3">
            <StepIcon state={step.state} />
            <span
              className={`text-sm ${
                step.state === "active"
                  ? "font-medium text-blue-700"
                  : step.state === "done"
                    ? "text-green-700"
                    : step.state === "error"
                      ? "text-red-700"
                      : "text-gray-400"
              }`}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
