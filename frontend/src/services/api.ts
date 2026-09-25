import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  UploadResponse,
  UploadStatusResponse,
  CreateDeckRequest,
  DeckResponse,
  DeckListItem,
  RetrievalResponse,
  OutlineResponse,
  SlideItem,
  GenerationStatusResponse,
  ExportResponse,
  UndoResponse,
  SSECallback,
} from "../types";

const API_BASE = "/api";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers as Record<string, string> },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function uploadURL(url: string): Promise<UploadResponse> {
  return request<UploadResponse>("/upload-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function checkUploadStatus(id: string): Promise<UploadStatusResponse> {
  return request<UploadStatusResponse>(`/upload/${id}`);
}

export async function createDeck(req: CreateDeckRequest): Promise<DeckResponse> {
  return request<DeckResponse>("/decks", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getDeck(id: string): Promise<DeckResponse> {
  return request<DeckResponse>(`/decks/${id}`);
}

export async function listDecks(): Promise<DeckListItem[]> {
  const res = await request<{ decks: DeckListItem[] }>("/decks");
  return res.decks;
}

export async function sendSyllabusFeedback(
  deckId: string,
  feedback: string,
): Promise<DeckResponse> {
  return request<DeckResponse>(`/decks/${deckId}/syllabus-feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

export async function approveSyllabus(deckId: string): Promise<DeckResponse> {
  return request<DeckResponse>(`/decks/${deckId}/syllabus-approve`, {
    method: "POST",
  });
}

export async function triggerRetrieval(deckId: string): Promise<RetrievalResponse> {
  return request<RetrievalResponse>(`/decks/${deckId}/retrieve`, {
    method: "POST",
  });
}

export async function generateOutline(deckId: string): Promise<OutlineResponse> {
  return request<OutlineResponse>(`/decks/${deckId}/generate-outline`, {
    method: "POST",
  });
}

export async function getSlides(deckId: string): Promise<SlideItem[]> {
  const res = await request<{ deck_id: string; slides: SlideItem[] }>(
    `/decks/${deckId}/slides`,
  );
  return res.slides;
}

export async function getGenerationStatus(
  deckId: string,
): Promise<GenerationStatusResponse> {
  return request<GenerationStatusResponse>(
    `/decks/${deckId}/generation-status`,
  );
}

export async function undoFeedback(deckId: string): Promise<UndoResponse> {
  return request<UndoResponse>(`/decks/${deckId}/undo`, { method: "POST" });
}

export async function exportDeck(deckId: string): Promise<ExportResponse> {
  return request<ExportResponse>(`/decks/${deckId}/export`, {
    method: "POST",
  });
}

export function streamSlideGeneration(
  deckId: string,
  onEvent: SSECallback,
): AbortController {
  const ctrl = new AbortController();
  fetchEventSource(`${API_BASE}/decks/${deckId}/generate-slides`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal: ctrl.signal,
    onmessage(msg) {
      if (msg.data) {
        try {
          onEvent({ event: msg.event || "message", data: JSON.parse(msg.data) });
        } catch {
          onEvent({ event: msg.event || "message", data: {} });
        }
      }
    },
    onerror(err) {
      onEvent({ event: "error", data: { error: String(err) } });
      throw err;
    },
    openWhenHidden: true,
  });
  return ctrl;
}

export function streamSlideFeedback(
  deckId: string,
  feedback: string,
  onEvent: SSECallback,
): AbortController {
  const ctrl = new AbortController();
  fetchEventSource(`${API_BASE}/decks/${deckId}/slide-feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
    signal: ctrl.signal,
    onmessage(msg) {
      if (msg.data) {
        try {
          onEvent({ event: msg.event || "message", data: JSON.parse(msg.data) });
        } catch {
          onEvent({ event: msg.event || "message", data: {} });
        }
      }
    },
    onerror(err) {
      onEvent({ event: "error", data: { error: String(err) } });
      throw err;
    },
    openWhenHidden: true,
  });
  return ctrl;
}
