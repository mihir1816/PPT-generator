import type { TopicSyllabus } from "../types";

interface SyllabusViewProps {
  syllabus: TopicSyllabus;
}

export default function SyllabusView({ syllabus }: SyllabusViewProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-lg font-semibold text-gray-900">
        {syllabus.title}
      </h3>
      {syllabus.estimated_slides && (
        <p className="mb-3 text-sm text-gray-500">
          ~{syllabus.estimated_slides} slides estimated
        </p>
      )}
      <ol className="space-y-3">
        {syllabus.topics.map((topic, i) => (
          <li key={i}>
            <div className="font-medium text-gray-800">
              {i + 1}. {topic.title}
              {topic.depth_hint && (
                <span className="ml-2 text-xs text-gray-400">
                  ({topic.depth_hint})
                </span>
              )}
            </div>
            {topic.subtopics.length > 0 && (
              <ul className="ml-6 mt-1 space-y-0.5">
                {topic.subtopics.map((sub, j) => (
                  <li key={j} className="text-sm text-gray-600">
                    <span className="mr-1 text-gray-400">--</span>
                    {sub}
                  </li>
                ))}
              </ul>
            )}
            {topic.notes && (
              <p className="ml-6 mt-1 text-xs text-gray-400 italic">
                {topic.notes}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
