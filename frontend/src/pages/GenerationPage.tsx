import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, Pencil, Zap, Trash2, Check } from "lucide-react";
import { useDeck } from "../hooks/useDeck";
import { AppShell } from "../components/layout/AppShell";
import { ThemeToggle } from "../components/ui/ThemeToggle";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ChatComposer } from "../components/feedback/ChatComposer";
import { ProgressStepper, type Stage } from "../components/progress/ProgressStepper";
import { SlideProgress } from "../components/progress/SlideProgress";
import * as api from "../services/api";
import type { SlideItem, SSEEvent } from "../types";

type Phase = "idle" | "retrieving" | "outlining" | "generating" | "done" | "error";

interface ChatMsg {
  from: "user" | "system";
  text: string;
}

export default function GenerationPage() {
  const { deckId } = useParams<{ deckId: string }>();
  const { deck, setDeck, slides, setSlides, loading, error, setError, fetchDeck, fetchSlides } =
    useDeck(deckId);

  const [phase, setPhase] = useState<Phase>("idle");
  const [generatingSlideId, setGeneratingSlideId] = useState<string | null>(null);
  const [totalSlides, setTotalSlides] = useState(0);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackRoundCount, setFeedbackRoundCount] = useState(0);
  const [activeSlide, setActiveSlide] = useState(0);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [startTime] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef<string | null>(null);
  const currentSlideMetaRef = useRef<{ position: number } | null>(null);

  useEffect(() => {
    if (phase !== "done" && phase !== "idle" && phase !== "error") {
      const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
      return () => clearInterval(timer);
    }
  }, [phase, startTime]);

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
          fetchSlides();
          break;
        case "generation_error":
          setError(data.error as string || "Generation error");
          break;
        case "error":
          setPhase("error");
          setError(data.error as string || "SSE connection error");
          break;
      }
    },
    [setSlides, setError, fetchDeck, fetchSlides],
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
        if (currentDeck.status === "ready_for_retrieval") {
          setPhase("retrieving");
          await api.triggerRetrieval(deckId);
        }

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
      setMessages((m) => [...m, { from: "user", text: feedback }]);

      abortRef.current?.abort();
      abortRef.current = api.streamSlideFeedback(
        deckId,
        feedback,
        (evt) => {
          handleSSEEvent(evt);
          if (evt.event === "generation_complete") {
            setFeedbackLoading(false);
            setPhase("done");
            setFeedbackRoundCount((c) => c + 1);
            fetchSlides();
            fetchDeck();
            setMessages((m) => [...m, { from: "system", text: "Slides updated successfully." }]);
          }
          if (evt.event === "generation_error" || evt.event === "error") {
            setFeedbackLoading(false);
            setMessages((m) => [...m, { from: "system", text: "Error updating slides." }]);
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
      setMessages((m) => [...m, { from: "system", text: "Undo applied." }]);
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

  const handleExport = async () => {
    if (!deckId) return;
    setExporting(true);
    setExportError(null);
    try {
      await api.exportDeck(deckId);
      window.open(`/api/decks/${deckId}/export/download`, "_blank");
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const isDone = phase === "done" || deck?.status === "completed";
  const isProcessing = phase !== "done" && phase !== "idle" && phase !== "error" && !feedbackLoading;

  const sortedSlides = [...slides].sort((a, b) => a.position - b.position);
  const currentSlide = sortedSlides[activeSlide];

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  // Processing view stages
  const stages: Stage[] = [
    {
      id: "retrieve",
      title: "Retrieving relevant content",
      detail: phase === "retrieving" ? `${formatElapsed(elapsed)}` : phase !== "idle" ? "done" : "",
      state:
        phase === "retrieving"
          ? "active"
          : ["outlining", "generating", "done"].includes(phase)
          ? "done"
          : phase === "error"
          ? "error"
          : "pending",
    },
    {
      id: "outline",
      title: "Generating slide outline",
      detail: phase === "outlining" ? `${formatElapsed(elapsed)}` : totalSlides > 0 ? `${totalSlides} slides mapped` : "",
      state:
        phase === "outlining"
          ? "active"
          : ["generating", "done"].includes(phase)
          ? "done"
          : phase === "error"
          ? "error"
          : "pending",
    },
    {
      id: "slides",
      title: "Writing your slides",
      detail: phase === "generating" ? "streaming..." : isDone ? "complete" : "",
      state:
        phase === "generating"
          ? "active"
          : isDone
          ? "done"
          : "pending",
      content:
        phase === "generating" ? (
          <SlideProgress
            completed={slides.length}
            total={totalSlides || slides.length}
            slideTitles={sortedSlides.map((s) => s.title)}
          />
        ) : undefined,
    },
  ];

  if (loading) {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="w-8 h-8 rounded-full border-[3px] border-line border-t-accent animate-spin" />
        </div>
      </AppShell>
    );
  }

  // Processing view (before done)
  if (isProcessing) {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <div className="flex items-center justify-between mb-1.5">
          <div>
            <h1 className="font-heading font-bold text-[26px] text-ink">
              {deck?.syllabus?.title || "Generating Presentation"}
            </h1>
            <p className="text-[13.5px] text-ink2 mt-1">
              Started {formatElapsed(elapsed)} ago
            </p>
          </div>
          <Badge tone="accent">IN PROGRESS</Badge>
        </div>

        <Card className="p-7 max-w-[760px] mt-6">
          <ProgressStepper stages={stages} />
        </Card>

        {error && (
          <div className="max-w-[760px] mt-4 rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn">
            {error}
          </div>
        )}
      </AppShell>
    );
  }

  // Error view
  if (phase === "error") {
    return (
      <AppShell navRight={<ThemeToggle />}>
        <h1 className="font-heading font-bold text-[26px] text-ink mb-4">
          {deck?.syllabus?.title || "Presentation"}
        </h1>
        <Card className="p-7 max-w-[760px]">
          <ProgressStepper stages={stages} />
        </Card>
        <div className="max-w-[760px] mt-4 space-y-3">
          <div className="rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn">
            {error || "An error occurred."}
          </div>
          <Button onClick={handleResume}>Resume Generation</Button>
        </div>
      </AppShell>
    );
  }

  // Slide review view (done)
  return (
    <AppShell
      navRight={
        <>
          <ThemeToggle />
          {feedbackRoundCount > 0 && (
            <Badge tone="success">{feedbackRoundCount} update{feedbackRoundCount > 1 ? "s" : ""}</Badge>
          )}
          <Button
            icon={<Download size={15} />}
            size="sm"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? "Exporting..." : "Export .pptx"}
          </Button>
        </>
      }
    >
      {exportError && (
        <div className="rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn mb-4">
          {exportError}
        </div>
      )}

      {error && (
        <div className="rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn mb-4">
          {error}
        </div>
      )}

      {/* Deck title */}
      <div className="mb-4">
        <h1 className="font-heading font-bold text-[22px] text-ink leading-snug">
          {deck?.syllabus?.title || deck?.title || "Presentation"}
        </h1>
        <p className="text-[13px] text-ink3 mt-0.5">
          {sortedSlides.length} slide{sortedSlides.length !== 1 ? "s" : ""}
          {feedbackRoundCount > 0 ? ` · ${feedbackRoundCount} revision${feedbackRoundCount !== 1 ? "s" : ""}` : ""}
        </p>
      </div>

      {/* Slide thumbnail strip */}
      {sortedSlides.length > 0 && (
        <div className="flex gap-2.5 overflow-x-auto pb-4 mb-1.5">
          {sortedSlides.map((slide, i) => {
            const isActive = i === activeSlide;
            const previewBp = slide.bullet_points?.[0] || "";
            return (
              <button
                key={slide.slide_id}
                onClick={() => setActiveSlide(i)}
                className={`rounded-2xl overflow-hidden border-2 flex-shrink-0 w-[130px] text-left transition-colors ${
                  isActive ? "border-accent bg-accent-bg" : "border-line bg-surface2"
                }`}
              >
                <div className="h-[70px] bg-surface border-b border-line px-2 py-1.5 overflow-hidden">
                  <div className="text-[9px] font-bold text-ink truncate">{slide.title}</div>
                  {previewBp && (
                    <div className="text-[8px] text-ink3 mt-0.5 line-clamp-3 leading-[1.3]">
                      {previewBp}
                    </div>
                  )}
                </div>
                <div
                  className={`px-2 py-1.5 text-[10.5px] truncate ${
                    isActive ? "text-ink font-bold" : "text-ink2 font-semibold"
                  }`}
                >
                  Slide {i + 1}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Slide content + sidebar */}
      <div className="flex gap-6 items-start">
        <div className="flex-1">
          {currentSlide ? (
            <div className="bg-[#FAF3E7] border border-line rounded-2xl p-12 flex flex-col gap-4.5 justify-center min-h-[340px]">
              <div
                className="text-[26px] font-bold text-[#2F4B3C]"
                style={{ fontFamily: "Georgia, serif" }}
              >
                {currentSlide.title}
              </div>
              {currentSlide.body && (
                <p className="text-[15px] text-[#3B3025] leading-relaxed whitespace-pre-wrap">
                  {currentSlide.body}
                </p>
              )}
              {currentSlide.bullet_points.length > 0 && (
                <div className="flex flex-col gap-3">
                  {currentSlide.bullet_points.map((bp, i) => (
                    <div
                      key={i}
                      className="text-[15px] text-[#3B3025] leading-relaxed pl-4 relative before:content-['•'] before:absolute before:left-0"
                    >
                      {bp}
                    </div>
                  ))}
                </div>
              )}
              {currentSlide.table_data && currentSlide.table_data.headers.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm text-[#3B3025]">
                    <thead>
                      <tr className="border-b border-[#2F4B3C]/20">
                        {currentSlide.table_data.headers.map((h, i) => (
                          <th key={i} className="px-3 py-2 text-left font-bold text-[#2F4B3C]">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {currentSlide.table_data.rows.map((row, i) => (
                        <tr key={i} className="border-b border-[#2F4B3C]/10">
                          {row.map((cell, j) => (
                            <td key={j} className="px-3 py-2">{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-surface2 border border-line rounded-2xl p-12 min-h-[340px] flex items-center justify-center">
              <p className="text-ink3">No slides generated yet.</p>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="w-[300px] flex-shrink-0 flex flex-col gap-4 sticky top-9 hidden lg:flex">
          {currentSlide && (
            <Card className="p-4.5">
              <div className="font-heading font-bold text-[14px] text-ink mb-2.5">
                Slide {activeSlide + 1} of {sortedSlides.length}
              </div>
              {currentSlide.speaker_notes && (
                <p className="text-xs text-ink3 mb-3 italic">{currentSlide.speaker_notes}</p>
              )}
              <div className="text-xs text-ink3">
                Layout: {currentSlide.layout_hint}
              </div>
            </Card>
          )}

          <Card className="p-4.5 flex flex-col gap-3">
            <div className="font-heading font-bold text-[14px] text-ink">
              Feedback
            </div>
            {messages.length > 0 && (
              <div className="flex flex-col gap-2 max-h-[220px] overflow-y-auto pr-1">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`rounded-2xl px-3.5 py-2.5 text-[12.5px] max-w-[240px] flex items-start gap-1.5 ${
                      m.from === "user"
                        ? "bg-accent-bg text-ink"
                        : "bg-surface border border-line text-ink2"
                    }`}
                  >
                    {m.from === "system" && (
                      <Check size={13} className="text-success mt-0.5 flex-shrink-0" aria-hidden />
                    )}
                    <span>{m.text}</span>
                  </div>
                ))}
              </div>
            )}
            <ChatComposer
              placeholder="Ask for a change..."
              onSend={handleSlideFeedback}
              disabled={feedbackLoading}
            />
            {feedbackRoundCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleUndo}
                disabled={feedbackLoading}
                className="self-start"
              >
                Undo Last
              </Button>
            )}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
