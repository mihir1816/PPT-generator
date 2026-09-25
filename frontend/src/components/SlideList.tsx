import type { SlideItem } from "../types";
import SlidePreview from "./SlidePreview";

interface SlideListProps {
  slides: SlideItem[];
  generatingSlideId?: string | null;
}

export default function SlideList({ slides, generatingSlideId }: SlideListProps) {
  const sorted = [...slides].sort((a, b) => a.position - b.position);

  if (sorted.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-400">
        No slides generated yet.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {sorted.map((slide) => (
        <SlidePreview
          key={slide.slide_id}
          slide={slide}
          isGenerating={slide.slide_id === generatingSlideId}
        />
      ))}
    </div>
  );
}
