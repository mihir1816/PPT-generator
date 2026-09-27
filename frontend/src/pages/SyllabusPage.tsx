import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { GripVertical, Pencil, X, Plus, Check } from "lucide-react";
import { useDeck } from "../hooks/useDeck";
import { AppShell } from "../components/layout/AppShell";
import { ThemeToggle } from "../components/ui/ThemeToggle";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ChatComposer } from "../components/feedback/ChatComposer";
import * as api from "../services/api";

interface ChatMsg {
  from: "user" | "system";
  text: string;
}

export default function SyllabusPage() {
  const { deckId } = useParams<{ deckId: string }>();
  const navigate = useNavigate();
  const { deck, setDeck, loading, error, setError, startPolling, stopPolling } =
    useDeck(deckId);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);

  useEffect(() => {
    if (
      deck &&
      (deck.status === "waiting_for_indexing" ||
        deck.status === "generating_syllabus")
    ) {
      startPolling(3000);
    }
    return () => stopPolling();
  }, [deck?.status, startPolling, stopPolling]);

  useEffect(() => {
    if (
      deck &&
      deck.status !== "syllabus_review" &&
      deck.status !== "generating_syllabus" &&
      deck.status !== "waiting_for_indexing" &&
      deck.status !== "pending"
    ) {
      navigate(`/decks/${deckId}/generate`);
    }
  }, [deck?.status, deckId, navigate]);

  const handleFeedback = useCallback(
    async (feedback: string) => {
      if (!deckId) return;
      setFeedbackLoading(true);
      setError(null);
      setMessages((m) => [...m, { from: "user", text: feedback }]);
      try {
        const updated = await api.sendSyllabusFeedback(deckId, feedback);
        setDeck(updated);
        setMessages((m) => [
          ...m,
          { from: "system", text: updated.message || "Syllabus updated." },
        ]);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Feedback failed";
        setError(msg);
        setMessages((m) => [...m, { from: "system", text: `Error: ${msg}` }]);
      } finally {
        setFeedbackLoading(false);
      }
    },
    [deckId, setDeck, setError],
  );

  const handleApprove = useCallback(async () => {
    if (!deckId) return;
    setApproving(true);
    setError(null);
    try {
      const updated = await api.approveSyllabus(deckId);
      setDeck(updated);
      if (
        updated.status === "ready_for_retrieval" ||
        updated.status === "retrieval_complete"
      ) {
        navigate(`/decks/${deckId}/generate`);
      } else {
        startPolling(3000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setApproving(false);
    }
  }, [deckId, setDeck, setError, startPolling, navigate]);

  if (loading) {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="w-8 h-8 rounded-full border-[3px] border-line border-t-accent animate-spin" />
        </div>
      </AppShell>
    );
  }

  if (!deck) {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <p className="text-warn font-bold">Deck not found.</p>
      </AppShell>
    );
  }

  const isReview = deck.status === "syllabus_review";
  const isWaiting = deck.status === "waiting_for_indexing";
  const isGenerating = deck.status === "generating_syllabus";
  const syllabus = deck.syllabus;

  return (
    <AppShell
      navRight={
        <>
          <ThemeToggle />
          <Badge tone="warn">SYLLABUS REVIEW</Badge>
        </>
      }
    >
      <div className="flex gap-7 items-start">
        {/* Main content */}
        <div className="max-w-[700px] flex-1">
          <h1 className="font-heading font-bold text-[26px] text-ink">
            {syllabus?.title || "Topic Syllabus"}
          </h1>
          <p className="text-[13.5px] text-ink2 mt-1.5 mb-5">
            {syllabus?.estimated_slides
              ? `~${syllabus.estimated_slides} slides estimated — `
              : ""}
            {isReview
              ? "reorder, edit or remove topics before we build your slides"
              : isGenerating
              ? "Generating syllabus..."
              : isWaiting
              ? "Waiting for documents to finish indexing..."
              : ""}
          </p>

          {isGenerating && (
            <div className="flex items-center gap-3 mb-5">
              <div className="w-6 h-6 rounded-full border-[3px] border-line border-t-accent animate-spin" />
              <span className="text-sm text-accent-ink font-bold">Generating syllabus...</span>
            </div>
          )}

          {isWaiting && (
            <div className="rounded-2xl bg-warn-bg border border-line p-4 text-sm text-warn mb-5">
              Documents are still being indexed. You'll be able to proceed once indexing completes.
            </div>
          )}

          {syllabus && (
            <div className="flex flex-col gap-3.5">
              {syllabus.topics.map((topic, i) => (
                <Card key={i} className="p-5 flex gap-3.5">
                  <div className="text-ink3 pt-0.5">
                    <GripVertical size={16} aria-hidden />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="font-heading font-bold text-[15.5px] text-ink">
                        {i + 1}. {topic.title}
                      </span>
                      {topic.depth_hint && (
                        <Badge
                          tone={topic.depth_hint.toLowerCase() === "detailed" ? "accent" : "neutral"}
                        >
                          {topic.depth_hint}
                        </Badge>
                      )}
                    </div>
                    {topic.subtopics.length > 0 && (
                      <div className="mt-2 flex flex-col gap-1">
                        {topic.subtopics.map((s, j) => (
                          <div
                            key={j}
                            className="flex items-center gap-2 text-ink2 text-[13px]"
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
                            {s}
                          </div>
                        ))}
                      </div>
                    )}
                    {topic.notes && (
                      <p className="text-[12.5px] text-ink3 italic mt-2">
                        {topic.notes}
                      </p>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn">
              {error}
            </div>
          )}

          {deck.message && (
            <div className="mt-4 rounded-2xl bg-accent-bg border border-line p-3 text-sm text-accent-ink">
              {deck.message}
            </div>
          )}
        </div>

        {/* Feedback sidebar */}
        <Card className="w-[300px] flex-shrink-0 p-4.5 flex flex-col gap-3 sticky top-9 hidden lg:flex">
          <div className="font-heading font-bold text-[14px] text-ink">
            Refine with feedback
          </div>
          {messages.length > 0 && (
            <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`rounded-2xl px-3.5 py-2.5 text-[12.5px] max-w-[220px] ${
                    m.from === "user"
                      ? "bg-accent-bg text-ink self-start"
                      : "bg-surface border border-line text-ink2"
                  }`}
                >
                  {m.text}
                </div>
              ))}
            </div>
          )}
          {isReview && (
            <ChatComposer
              placeholder="Tell it what to change..."
              onSend={handleFeedback}
              disabled={feedbackLoading}
            />
          )}
          <div className="border-t border-line mt-1 pt-3.5">
            <Button
              icon={<Check size={15} />}
              className="w-full justify-center"
              onClick={handleApprove}
              disabled={!isReview || approving}
            >
              {approving
                ? "Approving..."
                : isWaiting
                ? "Waiting for Indexing..."
                : "Approve & Generate Slides"}
            </Button>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
