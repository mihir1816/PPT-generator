import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../services/api";
import type { DeckResponse, SlideItem } from "../types";

export function useDeck(deckId: string | undefined) {
  const [deck, setDeck] = useState<DeckResponse | null>(null);
  const [slides, setSlides] = useState<SlideItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDeck = useCallback(async () => {
    if (!deckId) return;
    try {
      const d = await api.getDeck(deckId);
      setDeck(d);
      return d;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch deck");
    }
  }, [deckId]);

  const fetchSlides = useCallback(async () => {
    if (!deckId) return;
    try {
      const s = await api.getSlides(deckId);
      setSlides(s);
    } catch {
      // slides may not exist yet
    }
  }, [deckId]);

  useEffect(() => {
    if (deckId) {
      setLoading(true);
      Promise.all([fetchDeck(), fetchSlides()]).finally(() => setLoading(false));
    }
  }, [deckId, fetchDeck, fetchSlides]);

  const startPolling = useCallback(
    (intervalMs = 3000) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        const d = await fetchDeck();
        if (
          d &&
          d.status !== "waiting_for_indexing" &&
          d.status !== "generating_syllabus" &&
          d.status !== "retrieving" &&
          d.status !== "generating_outline" &&
          d.status !== "generating_slides"
        ) {
          stopPolling();
        }
      }, intervalMs);
    },
    [fetchDeck],
  );

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  return {
    deck,
    setDeck,
    slides,
    setSlides,
    loading,
    error,
    setError,
    fetchDeck,
    fetchSlides,
    startPolling,
    stopPolling,
  };
}
