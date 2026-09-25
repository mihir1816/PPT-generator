import type { SlideItem } from "../types";

interface SlidePreviewProps {
  slide: SlideItem;
  isGenerating?: boolean;
}

export default function SlidePreview({ slide, isGenerating }: SlidePreviewProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="font-medium text-gray-900">
          Slide {slide.position}: {slide.title}
        </h4>
        <span className="text-xs text-gray-400">{slide.layout_hint}</span>
      </div>

      {isGenerating && (
        <div className="mb-2 flex items-center gap-2 text-sm text-blue-600">
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Generating...
        </div>
      )}

      {slide.body && (
        <p className="mb-2 text-sm text-gray-700 whitespace-pre-wrap">{slide.body}</p>
      )}

      {slide.bullet_points.length > 0 && (
        <ul className="mb-2 space-y-1">
          {slide.bullet_points.map((bp, i) => (
            <li key={i} className="flex gap-2 text-sm text-gray-700">
              <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
              {bp}
            </li>
          ))}
        </ul>
      )}

      {slide.table_data && slide.table_data.headers.length > 0 && (
        <div className="mb-2 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                {slide.table_data.headers.map((h, i) => (
                  <th key={i} className="px-2 py-1 text-left font-medium text-gray-700">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {slide.table_data.rows.map((row, i) => (
                <tr key={i} className="border-b border-gray-100">
                  {row.map((cell, j) => (
                    <td key={j} className="px-2 py-1 text-gray-600">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {slide.speaker_notes && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700">
            Speaker Notes
          </summary>
          <p className="mt-1 text-xs text-gray-500 whitespace-pre-wrap">
            {slide.speaker_notes}
          </p>
        </details>
      )}
    </div>
  );
}
