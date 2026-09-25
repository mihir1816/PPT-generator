interface StreamingIndicatorProps {
  total: number;
  generated: number;
  currentSlide?: string | null;
}

export default function StreamingIndicator({
  total,
  generated,
  currentSlide,
}: StreamingIndicatorProps) {
  const pct = total > 0 ? Math.round((generated / total) * 100) : 0;

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium text-blue-800">
          Generating Slides: {generated}/{total}
        </span>
        <span className="text-blue-600">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-blue-200">
        <div
          className="h-full rounded-full bg-blue-600 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {currentSlide && (
        <p className="mt-2 text-xs text-blue-600">
          Generating: {currentSlide}
        </p>
      )}
    </div>
  );
}
