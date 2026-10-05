import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Link2, FileText, Check, Layers, X } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { ThemeToggle } from "../components/ui/ThemeToggle";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import * as api from "../services/api";
import type { TeacherPreferences, UploadStatusResponse } from "../types";

interface UploadEntry {
  fileId: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  documentId: string | null;
  error?: string | null;
}

const ACCEPTED = ".pdf,.pptx,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp";

const NEXT_STEPS = [
  { title: "Read your documents", detail: "Parsed, chunked and indexed automatically" },
  { title: "Draft a syllabus", detail: "You review and adjust before we build anything" },
  { title: "Write your slides", detail: "Streamed in as they're written" },
  { title: "Polish & export", detail: "Edit any slide, then download" },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [preferences, setPreferences] = useState<TeacherPreferences>({
    audience_level: "intermediate",
    tone: "formal",
    content_mode: "grounded",
  });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [urlValue, setUrlValue] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    return () => {
      cancelledRef.current.clear();
    };
  }, []);

  const pollUpload = useCallback(
    async (fileId: string): Promise<UploadStatusResponse | null> => {
      let result: UploadStatusResponse;
      while (!cancelledRef.current.has(fileId)) {
        await new Promise((r) => setTimeout(r, 2000));
        if (cancelledRef.current.has(fileId)) return null;
        result = await api.checkUploadStatus(fileId);
        setUploads((prev) =>
          prev.map((u) =>
            u.fileId === fileId
              ? { ...u, status: result.status, documentId: result.document_id, error: result.error_message }
              : u,
          ),
        );
        if (result.status === "completed" || result.status === "failed") return result;
      }
      return null;
    },
    [],
  );

  const handleFiles = useCallback(
    async (files: File[]) => {
      setError(null);
      for (const file of files) {
        try {
          const res = await api.uploadFile(file);
          const entry: UploadEntry = {
            fileId: res.file_id,
            filename: res.filename,
            status: "pending",
            documentId: null,
          };
          setUploads((prev) => [...prev, entry]);
          pollUpload(res.file_id);
        } catch (e) {
          setError(e instanceof Error ? e.message : "Upload failed");
        }
      }
    },
    [pollUpload],
  );

  const handleURL = useCallback(
    async () => {
      const trimmed = urlValue.trim();
      if (!trimmed || (!trimmed.startsWith("http://") && !trimmed.startsWith("https://"))) return;
      setError(null);
      try {
        const res = await api.uploadURL(trimmed);
        const entry: UploadEntry = {
          fileId: res.file_id,
          filename: trimmed,
          status: "pending",
          documentId: null,
        };
        setUploads((prev) => [...prev, entry]);
        setUrlValue("");
        pollUpload(res.file_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "URL upload failed");
      }
    },
    [urlValue, pollUpload],
  );

  const removeUpload = (fileId: string) => {
    cancelledRef.current.add(fileId);
    setUploads((prev) => prev.filter((u) => u.fileId !== fileId));
  };

  const completedDocIds = uploads
    .filter((u) => u.status === "completed" && u.documentId)
    .map((u) => u.documentId!);

  const canSubmit =
    completedDocIds.length > 0 && title.trim().length > 0 && description.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const deck = await api.createDeck({
        title: title.trim(),
        document_ids: completedDocIds,
        description: description.trim(),
        outline: null,
        preferences,
      });
      navigate(`/decks/${deck.deck_id}/syllabus`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create deck");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell navRight={<ThemeToggle />}>
      <h1 className="font-heading font-bold text-[26px] text-ink mb-1">
        Start a new deck
      </h1>
      <p className="text-[13.5px] text-ink2 mb-7">
        Upload your material, set a few preferences, and we'll take it from there.
      </p>

      <div className="flex gap-7 items-start">
        <div className="flex flex-col gap-6 max-w-[660px] flex-1">
          {/* Upload area */}
          <div>
            <h2 className="font-heading font-bold text-[13.5px] text-ink mb-2.5">
              Upload documents
            </h2>
            <label
              htmlFor="file-upload"
              className={`flex flex-col items-center gap-2.5 border-2 border-dashed rounded-2xl p-9 bg-surface cursor-pointer transition-colors ${
                dragOver ? "border-accent bg-accent-bg/30" : "border-line"
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files.length > 0) {
                  handleFiles(Array.from(e.dataTransfer.files));
                }
              }}
            >
              <div className="w-11 h-11 rounded-xl bg-accent-bg flex items-center justify-center -rotate-3">
                <Upload size={19} className="text-accent" aria-hidden />
              </div>
              <span className="text-[14.5px] text-ink">
                <span className="font-bold">Drag & drop your files</span>{" "}
                <span className="text-ink2">or</span>{" "}
                <span className="text-accent-ink font-bold">browse</span>
              </span>
              <span className="text-xs text-ink3">
                PDF, PPTX, DOCX, TXT, Images
              </span>
              <input
                id="file-upload"
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPTED}
                className="sr-only"
                onChange={(e) => {
                  if (e.target.files) {
                    handleFiles(Array.from(e.target.files));
                    e.target.value = "";
                  }
                }}
              />
            </label>

            {uploads.length > 0 && (
              <div className="flex flex-col gap-2 mt-2.5">
                {uploads.map((f) => (
                  <div
                    key={f.fileId}
                    className="flex items-center justify-between px-3.5 py-2.5 border border-line rounded-2xl bg-surface2"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <FileText size={16} className="text-ink2 flex-shrink-0" aria-hidden />
                      <div className="min-w-0">
                        <div className="text-[13px] font-semibold text-ink truncate">
                          {f.filename}
                        </div>
                        {f.error && (
                          <div className="text-[11px] text-warn">{f.error}</div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {f.status === "completed" && (
                        <div className="flex items-center gap-1.5 text-success text-xs font-bold">
                          <Check size={14} aria-hidden /> Parsed
                        </div>
                      )}
                      {f.status === "failed" && (
                        <span className="text-warn text-xs font-bold">Failed</span>
                      )}
                      {(f.status === "pending" || f.status === "processing") && (
                        <div className="w-20 h-1.5 rounded-full bg-line overflow-hidden">
                          <div className="w-[55%] h-full bg-accent animate-pulse" />
                        </div>
                      )}
                      <button
                        onClick={(e) => { e.preventDefault(); removeUpload(f.fileId); }}
                        className="text-ink3 hover:text-ink"
                      >
                        <X size={14} aria-hidden />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* URL input */}
          <div>
            <h2 className="font-heading font-bold text-[13.5px] text-ink mb-2.5">
              Or add a link
            </h2>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-2 border border-line rounded-2xl px-3.5 py-2.5 bg-surface2">
                <Link2 size={15} className="text-ink3 flex-shrink-0" aria-hidden />
                <input
                  type="url"
                  value={urlValue}
                  onChange={(e) => setUrlValue(e.target.value)}
                  placeholder="https://example.com/article"
                  className="flex-1 bg-transparent text-[13px] text-ink placeholder:text-ink3 outline-none"
                  onKeyDown={(e) => e.key === "Enter" && handleURL()}
                />
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleURL}
                disabled={!urlValue.trim()}
              >
                Add
              </Button>
            </div>
          </div>

          {/* Preferences */}
          <div className="flex gap-7 flex-wrap">
            <SegmentedControl
              label="Tone"
              options={[
                { value: "formal", label: "Formal" },
                { value: "creative", label: "Creative" },
              ]}
              value={preferences.tone}
              onChange={(v) => setPreferences((p) => ({ ...p, tone: v as "formal" | "creative" }))}
              disabled={submitting}
            />
            <SegmentedControl
              label="Content"
              options={[
                { value: "grounded", label: "Grounded" },
                { value: "mixed", label: "Mixed" },
              ]}
              value={preferences.content_mode}
              onChange={(v) => setPreferences((p) => ({ ...p, content_mode: v as "grounded" | "mixed" }))}
              disabled={submitting}
            />
            <SegmentedControl
              label="Level"
              options={[
                { value: "beginner", label: "Beginner" },
                { value: "intermediate", label: "Intermediate" },
                { value: "advanced", label: "Advanced" },
              ]}
              value={preferences.audience_level}
              onChange={(v) => setPreferences((p) => ({ ...p, audience_level: v as "beginner" | "intermediate" | "advanced" }))}
              disabled={submitting}
            />
            <div>
              <div className="text-[12.5px] font-bold text-ink2 font-body mb-2">Slides</div>
              <input
                type="number"
                min={5}
                max={50}
                placeholder="Auto"
                value={preferences.slide_count_hint ?? ""}
                onChange={(e) => setPreferences((p) => ({
                  ...p,
                  slide_count_hint: e.target.value ? Number(e.target.value) : null,
                }))}
                disabled={submitting}
                className="w-20 px-4 py-2 rounded-pill text-[13px] font-bold font-body border border-line bg-surface text-ink text-center outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
              />
            </div>
          </div>

          {/* Presentation Title */}
          <div>
            <h2 className="font-heading font-bold text-[13.5px] text-ink mb-2.5">
              Presentation Title <span className="text-warn">*</span>
            </h2>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Introduction to Machine Learning"
              disabled={submitting}
              maxLength={200}
              className="w-full border border-line rounded-2xl px-3.5 py-2.5 text-[13px] text-ink placeholder:text-ink3 bg-surface2 outline-none disabled:opacity-50"
            />
          </div>

          {/* Description */}
          <div>
            <h2 className="font-heading font-bold text-[13.5px] text-ink mb-2.5">
              Description
            </h2>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Tell us what this presentation should cover for your class..."
              disabled={submitting}
              className="w-full border border-line rounded-2xl px-3.5 py-3 text-[13px] text-ink placeholder:text-ink3 bg-surface2 outline-none resize-y disabled:opacity-50"
            />
          </div>

          {error && (
            <div className="rounded-2xl bg-warn-bg border border-line p-3 text-sm text-warn">
              {error}
            </div>
          )}

          <div>
            <Button onClick={handleSubmit} disabled={!canSubmit}>
              {submitting ? "Creating Presentation..." : "Generate Presentation"}
            </Button>
          </div>
        </div>

        {/* What happens next sidebar */}
        <Card className="w-[300px] flex-shrink-0 p-5.5 flex-col gap-4.5 hidden lg:flex">
          <div className="flex items-center gap-2 font-heading font-bold text-[14px] text-ink">
            <Layers size={15} className="text-accent" aria-hidden />
            What happens next
          </div>
          <div className="flex flex-col gap-4.5">
            {NEXT_STEPS.map((step, i) => (
              <div key={step.title} className="flex gap-3">
                <div className="w-6 h-6 rounded-full bg-accent-bg text-accent-ink flex items-center justify-center text-[11px] font-bold flex-shrink-0">
                  {i + 1}
                </div>
                <div>
                  <div className="text-[13px] font-bold text-ink">
                    {step.title}
                  </div>
                  <div className="text-xs text-ink2 mt-0.5">{step.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
