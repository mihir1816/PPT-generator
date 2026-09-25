import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import FileUploader from "../components/FileUploader";
import URLInput from "../components/URLInput";
import PreferencesForm from "../components/PreferencesForm";
import * as api from "../services/api";
import type { TeacherPreferences, UploadStatusResponse } from "../types";

interface UploadEntry {
  fileId: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  documentId: string | null;
  error?: string | null;
}

export default function HomePage() {
  const navigate = useNavigate();
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [preferences, setPreferences] = useState<TeacherPreferences>({
    audience_level: "intermediate",
    tone: "formal",
    content_mode: "grounded",
  });
  const [description, setDescription] = useState("");
  const [outline, setOutline] = useState("");
  const [showOutline, setShowOutline] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      const newEntries: UploadEntry[] = [];

      for (const file of files) {
        try {
          const res = await api.uploadFile(file);
          const entry: UploadEntry = {
            fileId: res.file_id,
            filename: res.filename,
            status: "pending",
            documentId: null,
          };
          newEntries.push(entry);
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
    async (url: string) => {
      setError(null);
      try {
        const res = await api.uploadURL(url);
        const entry: UploadEntry = {
          fileId: res.file_id,
          filename: url,
          status: "pending",
          documentId: null,
        };
        setUploads((prev) => [...prev, entry]);
        pollUpload(res.file_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "URL upload failed");
      }
    },
    [pollUpload],
  );

  const removeUpload = (fileId: string) => {
    cancelledRef.current.add(fileId);
    setUploads((prev) => prev.filter((u) => u.fileId !== fileId));
  };

  const completedDocIds = uploads
    .filter((u) => u.status === "completed" && u.documentId)
    .map((u) => u.documentId!);

  const allDone = uploads.length > 0 && uploads.every(
    (u) => u.status === "completed" || u.status === "failed",
  );

  const canSubmit =
    completedDocIds.length > 0 && description.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const deck = await api.createDeck({
        document_ids: completedDocIds,
        description: description.trim(),
        outline: showOutline && outline.trim() ? outline.trim() : null,
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
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-8 text-3xl font-bold text-gray-900">
        Teacher Content Generator
      </h1>

      <div className="space-y-6">
        <section>
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Upload Documents
          </h2>
          <FileUploader onFilesSelected={handleFiles} disabled={submitting} />
          <div className="mt-3">
            <p className="mb-2 text-center text-xs text-gray-400">or add a URL</p>
            <URLInput onSubmit={handleURL} disabled={submitting} />
          </div>

          {uploads.length > 0 && (
            <div className="mt-4 space-y-2">
              {uploads.map((u) => (
                <div
                  key={u.fileId}
                  className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm"
                >
                  <span className="truncate text-gray-700">{u.filename}</span>
                  <div className="flex items-center gap-2">
                    {u.status === "completed" && (
                      <span className="text-green-600">&#10003;</span>
                    )}
                    {u.status === "failed" && (
                      <span className="text-red-600" title={u.error || "Failed"}>
                        &#10007;
                      </span>
                    )}
                    {(u.status === "pending" || u.status === "processing") && (
                      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                    )}
                    <button
                      onClick={() => removeUpload(u.fileId)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      &times;
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Preferences
          </h2>
          <PreferencesForm
            preferences={preferences}
            onChange={setPreferences}
            description={description}
            onDescriptionChange={setDescription}
            outline={outline}
            onOutlineChange={setOutline}
            showOutline={showOutline}
            onToggleOutline={setShowOutline}
            disabled={submitting}
          />
        </section>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="w-full rounded-md bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Creating Presentation..." : "Generate Presentation"}
        </button>

        {!allDone && uploads.length > 0 && (
          <p className="text-center text-xs text-gray-400">
            Waiting for uploads to finish processing...
          </p>
        )}
      </div>
    </div>
  );
}
