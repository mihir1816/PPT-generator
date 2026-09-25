# Session 13 — Frontend React UI

## Goal
Build a React SPA that covers the full user flow: upload documents, set preferences, review/edit syllabus, view streaming slide generation, give slide feedback, and export to PPT. After this session, the product is usable end-to-end through a browser.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-12 complete
- `docs/sessions/PROJECT_OVERVIEW.md` — the 9-stage flow
- `src/app/api/` — all endpoint definitions (request/response shapes)
- OpenAPI docs at `http://localhost:8200/docs` — exact API contract

## Non-Negotiable Rules
- React 18+ with Vite + TypeScript
- TailwindCSS for styling (no component libraries — keep it simple)
- SSE via `@microsoft/fetch-event-source` (NOT native EventSource — POST endpoints need request body support)
- All API calls through a single `api.ts` service file
- Responsive layout (works on desktop, usable on tablet)
- No auth UI (single user for now)
- Error states for every async operation
- Loading states for every async operation
- Dockerized: `frontend/Dockerfile` with nginx to serve built SPA

## Project Setup
```
frontend/
├── package.json
├── vite.config.ts        # proxy /api → http://app:8000
├── tailwind.config.ts
├── tsconfig.json
├── Dockerfile            # multi-stage: node build → nginx serve
├── nginx.conf            # serve SPA + proxy /api to backend
├── src/
│   ├── main.tsx
│   ├── App.tsx            # router setup
│   ├── types/
│   │   └── index.ts       # TypeScript types matching backend schemas
│   ├── services/
│   │   └── api.ts         # all API calls + SSE helpers
│   ├── hooks/
│   │   ├── useFetchSSE.ts  # SSE via fetch (NOT native EventSource — supports POST)
│   │   └── useDeck.ts      # deck state management hook
│   ├── pages/
│   │   ├── HomePage.tsx        # upload + create deck
│   │   ├── SyllabusPage.tsx    # syllabus review + feedback loop #1
│   │   ├── GenerationPage.tsx  # slide generation + streaming + feedback loop #2
│   │   └── DecksListPage.tsx   # list past decks
│   └── components/
│       ├── FileUploader.tsx     # drag-drop + file select
│       ├── URLInput.tsx         # add article URL
│       ├── PreferencesForm.tsx  # tone, content mode, level, description, outline
│       ├── SyllabusView.tsx     # display topic syllabus
│       ├── SyllabusFeedback.tsx # feedback input for syllabus
│       ├── SlidePreview.tsx     # single slide card
│       ├── SlideList.tsx        # all slides with scroll
│       ├── SlideFeedback.tsx    # feedback input for slides
│       ├── StreamingIndicator.tsx # progress during slide generation
│       ├── ProcessingSteps.tsx   # progress for retrieval → outline → generation
│       ├── StatusBadge.tsx      # deck status pill
│       └── ExportButton.tsx     # export + download
```

## Pages Detail

### `HomePage.tsx` — Stage 1: User Input
```
Layout:
  ┌─────────────────────────────────────────────┐
  │  Teacher Content Generator                   │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  Upload Documents                     │   │
  │  │  [Drag & drop or click to upload]     │   │
  │  │  Supported: PDF, PPTX, DOCX, Images  │   │
  │  │  ─── or ───                           │   │
  │  │  [Add article URL] [+]               │   │
  │  │                                       │   │
  │  │  Uploaded: file1.pdf ✓  file2.docx ✓ │   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  Tone:    [Formal] [Creative]               │
  │  Content: [Grounded] [Mixed]                │
  │  Level:   [Beginner] [Intermediate] [Adv]   │
  │                                              │
  │  Description: [textarea]                     │
  │  Outline:     [None] [Provide outline]       │
  │    (if outline selected → textarea appears)  │
  │                                              │
  │  [Generate Presentation →]                   │
  └─────────────────────────────────────────────┘

On submit:
  1. Upload files via POST /api/upload (parallel)
  2. Wait for all uploads to return document_ids
  3. POST /api/decks with document_ids + preferences
  4. Navigate to SyllabusPage with deck_id
```

### `SyllabusPage.tsx` — Stage 3: Syllabus Review
```
Layout:
  ┌─────────────────────────────────────────────┐
  │  Topic Syllabus                    [Status] │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  1. Introduction to ML               │   │
  │  │     ├─ What is Machine Learning       │   │
  │  │     ├─ Types of Learning              │   │
  │  │     └─ Real-world Applications        │   │
  │  │  2. Linear Regression                 │   │
  │  │     ├─ Theory                         │   │
  │  │     └─ Implementation                 │   │
  │  │  3. ...                               │   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  Feedback: [textarea]                 │   │
  │  │  "Remove topic 3, expand topic 2..."  │   │
  │  │                        [Send Feedback]│   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  Document Processing: [████████░░] 80%      │
  │                                              │
  │  [Approve Syllabus & Continue →]            │
  │  (disabled until docs indexed)               │
  └─────────────────────────────────────────────┘

Behavior:
  - Poll GET /api/decks/{id} for document indexing status
  - POST /api/decks/{id}/syllabus-feedback on feedback submit
  - Syllabus view re-renders with updated topics
  - "Approve" enabled only when all docs indexed
  - POST /api/decks/{id}/syllabus-approve → navigate to GenerationPage
```

### `GenerationPage.tsx` — Stages 5-9: Generation + Feedback + Export
```
Layout:
  ┌─────────────────────────────────────────────┐
  │  Presentation: "ML Basics"       [Status]   │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  Slide 1: Introduction to ML    ✓    │   │
  │  │  ─────────────────────────────────── │   │
  │  │  • Machine Learning is a subset...   │   │
  │  │  • Three main types: supervised...   │   │
  │  │                                       │   │
  │  │  Speaker notes: Start by asking...   │   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  Slide 2: [Generating... ███░░░]     │   │
  │  │  Tokens streaming in real-time...     │   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  ┌──────────────────────────────────────┐   │
  │  │  Feedback: [textarea]                 │   │
  │  │  "Expand slide 3, remove slide 5..." │   │
  │  │                   [Send] [Undo Last] │   │
  │  └──────────────────────────────────────┘   │
  │                                              │
  │  [Export to PPT ↓]                          │
  └─────────────────────────────────────────────┘

Behavior:
  - On mount: auto-triggers retrieve → outline → generate-slides
  - ProcessingSteps component shows progress through each phase:
      Step 1: "Retrieving relevant content..." (POST /retrieve)
      Step 2: "Generating slide outline..." (POST /generate-outline)
      Step 3: "Generating slides..." (POST /generate-slides via SSE)
    Each step shows ✓ when complete, spinner when active, ○ when pending.
    This gives the user visibility during the 30-60s between approval and first slide.
  - SSE via @microsoft/fetch-event-source (NOT native EventSource)
  - Each slide card appears as generated
  - On SSE disconnect: show already-generated slides + "Resume" button
    (calls GET /generation-status, then re-POSTs /generate-slides for remaining)
  - After all slides complete → feedback section enabled
  - Slide feedback → SSE stream for regenerated slides only
  - Undo restores previous state (outline + slide content from snapshot)
  - Export button → POST /api/decks/{id}/export → download file
```

## Key Components

### `services/api.ts`
```typescript
const API_BASE = "/api"

export async function uploadFile(file: File): Promise<UploadResponse>
export async function uploadURL(url: string): Promise<UploadResponse>
export async function checkUploadStatus(id: string): Promise<StatusResponse>
export async function createDeck(req: CreateDeckRequest): Promise<DeckResponse>
export async function getDeck(id: string): Promise<DeckResponse>
export async function listDecks(): Promise<DeckResponse[]>
export async function sendSyllabusFeedback(deckId: string, feedback: string): Promise<SyllabusResponse>
export async function approveSyllabus(deckId: string): Promise<StatusResponse>
export async function triggerRetrieval(deckId: string): Promise<StatusResponse>
export async function generateOutline(deckId: string): Promise<OutlineResponse>
export function streamSlideGeneration(deckId: string, onEvent: SSECallback): AbortController
    // Uses fetchEventSource with POST — NOT native EventSource
export async function getSlides(deckId: string): Promise<SlideResponse[]>
export async function getGenerationStatus(deckId: string): Promise<GenerationStatus>
export function streamSlideFeedback(deckId: string, feedback: string, onEvent: SSECallback): AbortController
    // Uses fetchEventSource with POST + body — NOT native EventSource
export async function undoFeedback(deckId: string): Promise<OutlineResponse>
export async function exportDeck(deckId: string): Promise<ExportResponse>
```

### `hooks/useFetchSSE.ts`
```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source'

/**
 * WHY NOT native EventSource?
 * Native EventSource only supports GET requests. Our slide generation
 * and feedback endpoints are POST (they need request bodies).
 * @microsoft/fetch-event-source uses fetch() internally so it supports
 * POST + body + SSE streaming.
 */
function useFetchSSE(config: {
  url: string,
  method?: 'GET' | 'POST',
  body?: object,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Error) => void,
}): {
  start: () => void, close: () => void, connected: boolean, error: string | null
}

/**
 * Reconnection strategy:
 * On disconnect, the hook:
 * 1. Calls GET /api/decks/{id}/generation-status to see progress
 * 2. Calls GET /api/decks/{id}/slides to load already-generated slides
 * 3. Offers user a "Resume" button that re-POSTs /generate-slides
 *    (backend skips already-generated slides via outline status check)
 */
```

### `frontend/Dockerfile`
```dockerfile
# Stage 1: Build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

### `frontend/nginx.conf`
```nginx
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # SSE support:
        proxy_set_header Cache-Control no-cache;
        proxy_buffering off;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Flow
```
1. Initialize React project: npm create vite@latest frontend -- --template react-ts
2. Install TailwindCSS + @microsoft/fetch-event-source + configure
3. Create types/index.ts matching backend schemas
4. Create services/api.ts
5. Create hooks (useSSE, useDeck)
6. Create all components
7. Create all pages
8. Set up React Router in App.tsx
9. Configure vite proxy for dev
10. Create Dockerfile + nginx.conf
11. Build + test in Docker
```

## Verification
```bash
# 1. Dev mode (outside Docker)
cd frontend && npm run dev
# Open http://localhost:5173 → app loads

# 2. Docker build
docker compose up -d --build frontend
# Open http://localhost:3000 → app loads

# 3. Full flow walkthrough (in browser):
#    a. Upload a PDF → see upload progress → status "completed"
#    b. Set preferences (tone, content, level)
#    c. Write description → click Generate
#    d. Syllabus appears → send feedback → syllabus updates
#    e. Approve syllabus → processing indicator
#    f. Slides stream in one by one (SSE)
#    g. Send slide feedback → affected slides regenerate
#    h. Click Export → PPTX downloads
#    i. Open PPTX in PowerPoint/LibreOffice → looks correct

# 4. Error states
#    - Upload invalid file → error message shown
#    - Network disconnect during SSE → reconnect or error shown

# 5. Responsive
#    - Resize browser to tablet width → layout adjusts
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 13 ✅, note frontend working end-to-end, next → Session 14
