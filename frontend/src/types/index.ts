export interface UploadResponse {
  file_id: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
}

export interface UploadStatusResponse {
  file_id: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  document_id: string | null;
  error_message: string | null;
}

export interface TeacherPreferences {
  audience_level: "beginner" | "intermediate" | "advanced";
  tone: "formal" | "creative";
  content_mode: "grounded" | "mixed";
  slide_count_hint?: number | null;
  additional_instructions?: string | null;
}

export interface CreateDeckRequest {
  title: string;
  document_ids: string[];
  description: string;
  outline?: string | null;
  preferences: TeacherPreferences;
}

export interface SyllabusTopic {
  title: string;
  subtopics: string[];
  depth_hint?: string | null;
  notes?: string | null;
}

export interface TopicSyllabus {
  title: string;
  topics: SyllabusTopic[];
  audience_level: string;
  estimated_slides?: number | null;
}

export interface DeckResponse {
  deck_id: string;
  title: string;
  status: string;
  syllabus: TopicSyllabus | null;
  syllabus_status: string;
  version: number;
  document_ids: string[];
  message?: string | null;
}

export interface DeckListItem {
  deck_id: string;
  title: string;
  status: string;
  syllabus_status: string;
  teacher_query: string;
  version: number;
  slide_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface SlideOutline {
  id: string;
  position: number;
  type: string;
  title: string;
  key_points: string[];
  layout_hint: string;
  source_chunk_ids: string[];
  spans_slides: boolean;
  table_continuation: boolean;
  status: "pending" | "needs_regeneration" | "generated";
}

export interface SlideItem {
  slide_id: string;
  position: number;
  title: string;
  body: string;
  bullet_points: string[];
  table_data: { headers: string[]; rows: string[][] } | null;
  speaker_notes: string;
  layout_hint: string;
}

export interface TopicCoverageItem {
  topic: string;
  coverage: string;
  chunk_count: number;
}

export interface RetrievalResponse {
  deck_id: string;
  status: string;
  total_chunks: number;
  queries_generated: number;
  coverage: TopicCoverageItem[];
  gaps: string[];
  message?: string | null;
}

export interface OutlineResponse {
  deck_id: string;
  status: string;
  outline: SlideOutline[];
  slide_count: number;
  message?: string | null;
}

export interface GenerationStatusResponse {
  deck_id: string;
  status: string;
  total: number;
  generated: number;
  pending: string[];
}

export interface ExportResponse {
  deck_id: string;
  download_url: string;
  filename: string;
  file_size: number;
}

export interface UndoResponse {
  success: boolean;
  message: string;
  outline: Record<string, unknown>[];
  slides: Record<string, unknown>[];
  version: number;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export type SSECallback = (event: SSEEvent) => void;
