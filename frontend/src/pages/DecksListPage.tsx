import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import * as api from "../services/api";
import type { DeckListItem } from "../types";

export default function DecksListPage() {
  const [decks, setDecks] = useState<DeckListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .listDecks()
      .then(setDecks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load decks"))
      .finally(() => setLoading(false));
  }, []);

  const getDeckLink = (d: DeckListItem) => {
    if (
      d.status === "syllabus_review" ||
      d.status === "generating_syllabus" ||
      d.status === "waiting_for_indexing" ||
      d.status === "pending"
    ) {
      return `/decks/${d.deck_id}/syllabus`;
    }
    return `/decks/${d.deck_id}/generate`;
  };

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <span className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">My Presentations</h1>
        <Link
          to="/"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + New
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {decks.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          No presentations yet. Create one to get started.
        </p>
      ) : (
        <div className="space-y-3">
          {decks.map((d) => (
            <div
              key={d.deck_id}
              onClick={() => navigate(getDeckLink(d))}
              className="cursor-pointer rounded-lg border border-gray-200 bg-white p-4 transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-gray-900">
                    {d.teacher_query}
                  </p>
                  <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
                    <span>v{d.version}</span>
                    {d.slide_count > 0 && <span>{d.slide_count} slides</span>}
                    {d.created_at && (
                      <span>
                        {new Date(d.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <StatusBadge status={d.status} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
