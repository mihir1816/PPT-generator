import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useDeck } from "../hooks/useDeck";
import SyllabusView from "../components/SyllabusView";
import SyllabusFeedback from "../components/SyllabusFeedback";
import StatusBadge from "../components/StatusBadge";
import * as api from "../services/api";

export default function SyllabusPage() {
  const { deckId } = useParams<{ deckId: string }>();
  const navigate = useNavigate();
  const { deck, setDeck, loading, error, setError, startPolling, stopPolling } =
    useDeck(deckId);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [approving, setApproving] = useState(false);

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
      try {
        const updated = await api.sendSyllabusFeedback(deckId, feedback);
        setDeck(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Feedback failed");
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
      <div className="flex min-h-[50vh] items-center justify-center">
        <span className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (!deck) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-red-600">Deck not found.</p>
      </div>
    );
  }

  const isReview = deck.status === "syllabus_review";
  const isWaiting = deck.status === "waiting_for_indexing";

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Topic Syllabus</h1>
        <StatusBadge status={deck.status} />
      </div>

      {deck.syllabus && <SyllabusView syllabus={deck.syllabus} />}

      {deck.status === "generating_syllabus" && (
        <div className="mt-4 flex items-center gap-2 text-sm text-blue-600">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Generating syllabus...
        </div>
      )}

      {isReview && (
        <div className="mt-6">
          <SyllabusFeedback
            onSubmit={handleFeedback}
            loading={feedbackLoading}
          />
        </div>
      )}

      {isWaiting && (
        <div className="mt-4 rounded-md bg-orange-50 p-3 text-sm text-orange-700">
          Documents are still being indexed. You'll be able to proceed once
          indexing completes.
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {deck.message && (
        <div className="mt-4 rounded-md bg-blue-50 p-3 text-sm text-blue-700">
          {deck.message}
        </div>
      )}

      <div className="mt-6">
        <button
          onClick={handleApprove}
          disabled={!isReview || approving}
          className="w-full rounded-md bg-green-600 px-4 py-3 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          {approving
            ? "Approving..."
            : isWaiting
              ? "Waiting for Document Indexing..."
              : "Approve Syllabus & Continue"}
        </button>
      </div>
    </div>
  );
}
