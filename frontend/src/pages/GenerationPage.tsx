import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useDeck } from "../hooks/useDeck";
import SlideList from "../components/SlideList";
import SlideFeedback from "../components/SlideFeedback";
import StreamingIndicator from "../components/StreamingIndicator";
import ProcessingSteps from "../components/ProcessingSteps";
import StatusBadge from "../components/StatusBadge";
import ExportButton from "../components/ExportButton";
import * as api from "../services/api";
import type { SlideItem, SSEEvent } from "../types";

type Phase = "idle" | "retrieving" | "outlining" | "generating" | "done" | "error";

export default function GenerationPage() {
  const { deckId } = useParams<{ deckId: string }>();
  const { deck, setDeck, slides, setSlides, loading, error, setError, fetchDeck, fetchSlides } =
    useDeck(deckId);

  const [phase, setPhase] = useState<Phase>("idle");
  const [generatingSlideId, setGeneratingSlideId] = useState<string | null>(null);
  const [totalSlides, setTotalSlides] = useState(0);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackRoundCount, setFeedbackRoundCount] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef<string | null>(null);
  const currentSlideMetaRef = useRef<{ position: number } | null>(null);

  const handleSSEEvent = useCallback(
    (evt: SSEEvent) => {
      const data = evt.data as Record<string, unknown>;
      switch (evt.event) {
        case "slide_start":
          setGeneratingSlideId(data.slide_id as string);
          currentSlideMetaRef.current = { position: data.position as number };
          break;
        case "slide_content": {
          const position = currentSlideMetaRef.current?.position ?? 0;
          const slide: SlideItem = {
            slide_id: data.slide_id as string,
            position,
            title: (data.title as string) || "",
            body: (data.body as string) || "",
            bullet_points: (data.bullet_points as string[]) || [],
            table_data: (data.table_data as SlideItem["table_data"]) || null,
            speaker_notes: (data.speaker_notes as string) || "",
            layout_hint: (data.layout_hint as string) || "bullet",
          };
          setSlides((prev) => {
            const idx = prev.findIndex((s) => s.slide_id === slide.slide_id);
            if (idx >= 0) {
              const next = [...prev];
              next[idx] = slide;
              return next;
            }
            return [...prev, slide];
          });
          break;
        }
        case "slide_complete":
          setGeneratingSlideId(null);
          currentSlideMetaRef.current = null;
          break;
        case "generation_complete":
          setPhase("done");
          setGeneratingSlideId(null);
          fetchDeck();
          break;
        case "generation_error":
          setError(data.error as string || "Generation error");
          setPhase("error");
          setGeneratingSlideId(null);
          break;
        case "error":
          setPhase("error");
          setError(data.error as string || "SSE connection error");
          break;
      }
    },
    [setSlides, setError, fetchDeck],
  );

  const runPipeline = useCallback(async () => {
    if (!deckId || startedRef.current === deckId) return;
    startedRef.current = deckId;
    setError(null);

    try {
      const currentDeck = await api.getDeck(deckId);

      if (currentDeck.status === "completed" || currentDeck.status === "outline_ready") {
        setDeck(currentDeck);
        await fetchSlides();
        setPhase("done");
        return;
      }

      if (
        currentDeck.status === "ready_for_retrieval" ||
        currentDeck.status === "retrieval_complete" ||
        currentDeck.status === "generating_outline" ||
        currentDeck.status === "generating_slides"
      ) {
        // Step 1: Retrieve
        if (currentDeck.status === "ready_for_retrieval") {
          setPhase("retrieving");
          await api.triggerRetrieval(deckId);
        }

        // Step 2: Outline
        const afterRetrieval = await api.getDeck(deckId);
        setDeck(afterRetrieval);
        if (
          afterRetrieval.status === "retrieval_complete" ||
          afterRetrieval.status === "generating_outline"
        ) {
          setPhase("outlining");
          const outlineRes = await api.generateOutline(deckId);
          setTotalSlides(outlineRes.slide_count);
        }

        // Step 3: Generate slides via SSE
        const afterOutline = await api.getDeck(deckId);
        setDeck(afterOutline);
        if (
          afterOutline.status === "outline_ready" ||
          afterOutline.status === "generating_slides"
        ) {
          setPhase("generating");
          const genStatus = await api.getGenerationStatus(deckId);
          setTotalSlides(genStatus.total);
          if (genStatus.generated > 0) {
            await fetchSlides();
          }
          abortRef.current = api.streamSlideGeneration(deckId, handleSSEEvent);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setPhase("error");
    }
  }, [deckId, setDeck, setError, fetchSlides, handleSSEEvent]);

  useEffect(() => {
    if (deckId && !startedRef.current) {
      runPipeline();
    }
    return () => {
      abortRef.current?.abort();
    };
  }, [deckId, runPipeline]);

  const handleSlideFeedback = useCallback(
    async (feedback: string) => {
      if (!deckId) return;
      setFeedbackLoading(true);
      setError(null);
      setPhase("generating");

      abortRef.current?.abort();
      abortRef.current = api.streamSlideFeedback(
        deckId,
        feedback,
        (evt) => {
          handleSSEEvent(evt);
          if (evt.event === "generation_complete") {
            setFeedbackLoading(false);
            setFeedbackRoundCount((c) => c + 1);
          }
          if (evt.event === "generation_error" || evt.event === "error") {
            setFeedbackLoading(false);
          }
        },
      );
    },
    [deckId, setError, handleSSEEvent],
  );

  const handleUndo = useCallback(async () => {
    if (!deckId) return;
    setFeedbackLoading(true);
    setError(null);
    try {
      await api.undoFeedback(deckId);
      await fetchDeck();
      await fetchSlides();
      setFeedbackRoundCount((c) => Math.max(0, c - 1));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Undo failed");
    } finally {
      setFeedbackLoading(false);
    }
  }, [deckId, setError, fetchDeck, fetchSlides]);

  const handleResume = useCallback(async () => {
    if (!deckId) return;
    setError(null);
    setPhase("generating");
    abortRef.current?.abort();

    try {
      await fetchSlides();
      abortRef.current = api.streamSlideGeneration(deckId, handleSSEEvent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resume failed");
      setPhase("error");
    }
  }, [deckId, setError, fetchSlides, handleSSEEvent]);

  const steps = [
    {
      label: "Retrieving relevant content...",
      state:
        phase === "retrieving"
          ? ("active" as const)
          : phase === "outlining" ||
              phase === "generating" ||
              phase === "done"
            ? ("done" as const)
            : phase === "error"
              ? ("error" as const)
              : ("pending" as const),
    },
    {
      label: "Generating slide outline...",
      state:
        phase === "outlining"
          ? ("active" as const)
          : phase === "generating" || phase === "done"
            ? ("done" as const)
            : phase === "error"
              ? ("error" as const)
              : ("pending" as const),
    },
    {
      label: "Generating slides...",
      state:
        phase === "generating"
          ? ("active" as const)
          : phase === "done"
            ? ("done" as const)
            : ("pending" as const),
    },
  ];

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <span className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  const isDone = phase === "done" || deck?.status === "completed";
  const isGenerating = phase === "generating";

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">
          {deck?.syllabus?.title || "Presentation"}
        </h1>
        {deck && <StatusBadge status={deck.status} />}
      </div>

      {phase !== "done" && phase !== "idle" && (
        <div className="mb-6">
          <ProcessingSteps steps={steps} />
        </div>
      )}

      {isGenerating && (
        <div className="mb-6">
          <StreamingIndicator
            total={totalSlides || slides.length}
            generated={slides.length}
            currentSlide={generatingSlideId}
          />
        </div>
      )}

      <div className="mb-6">
        <SlideList slides={slides} generatingSlideId={generatingSlideId} />
      </div>

      {phase === "error" && (
        <div className="mb-6 space-y-2">
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error || "An error occurred."}
          </div>
          <button
            onClick={handleResume}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Resume Generation
          </button>
        </div>
      )}

      {error && phase !== "error" && (
        <div className="mb-6 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {isDone && (
        <>
          <div className="mb-6">
            <SlideFeedback
              onSubmit={handleSlideFeedback}
              onUndo={handleUndo}
              disabled={feedbackLoading}
              loading={feedbackLoading}
              canUndo={feedbackRoundCount > 0}
            />
          </div>
          <div className="flex justify-end">
            <ExportButton deckId={deckId!} />
          </div>
        </>
      )}
    </div>
  );
}
