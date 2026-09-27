import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Plus, FileText } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { ThemeToggle } from "../components/ui/ThemeToggle";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import * as api from "../services/api";
import type { DeckListItem } from "../types";

type Tone = "success" | "warn" | "accent";

function statusTone(status: string): Tone {
  if (status === "completed") return "success";
  if (status === "failed") return "warn";
  return "accent";
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "Draft",
    generating_syllabus: "Generating...",
    syllabus_review: "Draft",
    waiting_for_indexing: "Indexing...",
    ready_for_retrieval: "Ready",
    retrieving: "Retrieving...",
    retrieval_complete: "Retrieved",
    generating_outline: "Outlining...",
    outline_ready: "Outlined",
    generating_slides: "Generating...",
    completed: "Ready",
    failed: "Failed",
  };
  return map[status] || status.replace(/_/g, " ");
}

function getDeckLink(d: DeckListItem) {
  if (
    d.status === "syllabus_review" ||
    d.status === "generating_syllabus" ||
    d.status === "waiting_for_indexing" ||
    d.status === "pending"
  ) {
    return `/decks/${d.deck_id}/syllabus`;
  }
  return `/decks/${d.deck_id}/generate`;
}

export default function DecksListPage() {
  const [decks, setDecks] = useState<DeckListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .listDecks()
      .then(setDecks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load decks"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = decks.filter((d) =>
    d.teacher_query.toLowerCase().includes(search.toLowerCase()),
  );

  if (loading) {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="w-8 h-8 rounded-full border-[3px] border-line border-t-accent animate-spin" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell navRight={<ThemeToggle />}>
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-[26px] text-ink">Your decks</h1>
          <p className="text-[13.5px] text-ink2 mt-1">
            {decks.length} presentation{decks.length !== 1 ? "s" : ""}, ready whenever your class is.
          </p>
        </div>
        <Button icon={<Plus size={15} />} onClick={() => navigate("/")}>
          New Deck
        </Button>
      </div>

      {error && (
        <div className="rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn mb-6">
          {error}
        </div>
      )}

      <div className="relative mb-6 max-w-[280px]">
        <Search
          size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-ink3"
          aria-hidden
        />
        <input
          type="text"
          placeholder="Search decks..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-surface border border-line rounded-lg pl-9 pr-3 py-2 text-[13px] text-ink placeholder:text-ink3 outline-none"
        />
      </div>

      {filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-ink3">
          {decks.length === 0
            ? "No presentations yet. Create one to get started."
            : "No decks match your search."}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4.5">
          {filtered.map((d) => (
            <button
              key={d.deck_id}
              className="text-left bg-surface2 border border-line rounded-card overflow-hidden shadow-[0_2px_0_var(--color-line)] hover:-translate-y-0.5 transition-transform"
              onClick={() => navigate(getDeckLink(d))}
            >
              <div className="h-[110px] bg-bg flex items-center justify-center">
                <div className="w-11 h-11 rounded-xl bg-accent-bg flex items-center justify-center -rotate-3">
                  <FileText size={20} className="text-accent" aria-hidden />
                </div>
              </div>
              <div className="p-4">
                <div className="font-heading font-bold text-[14.5px] text-ink leading-snug mb-2 line-clamp-2">
                  {d.teacher_query}
                </div>
                <div className="flex items-center justify-between">
                  <Badge tone={statusTone(d.status)}>{statusLabel(d.status)}</Badge>
                  {d.slide_count > 0 && (
                    <span className="text-xs text-ink3">{d.slide_count} slides</span>
                  )}
                </div>
              </div>
            </button>
          ))}
          <button
            onClick={() => navigate("/")}
            className="border-2 border-dashed border-line rounded-card flex flex-col items-center justify-center gap-2.5 min-h-[198px] text-ink2"
          >
            <div className="w-10 h-10 rounded-full bg-accent-bg flex items-center justify-center">
              <Plus size={18} className="text-accent" aria-hidden />
            </div>
            <span className="text-[13.5px] font-bold">New Deck</span>
          </button>
        </div>
      )}
    </AppShell>
  );
}
