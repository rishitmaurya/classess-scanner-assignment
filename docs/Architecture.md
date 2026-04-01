Make a proper md file of this... without modifying the content at all.

1. Overview
Curious is a standalone evaluation engine that reads handwritten student assignments via camera, evaluates them against teacher-provided or auto-generated rubrics using Google Gemini Vision AI, and returns scored results with highlighted answer regions. It operates as an independent service with its own APIs, designed to be embedded into the Classess platform.

Users:

Teacher — Creates assignments, provides/approves expected answers, receives evaluation reports
Student — Scans handwritten pages, views results with feedback, submits for teacher review
2. System Architecture
Refer to: Diagram 1 — System Architecture Overview

2.1 Layer Breakdown
Layer	Components	Responsibility
Client	Web App, Mobile App, Desktop App, Phone Scanner	UI, camera access, results display
API	FastAPI Backend	REST endpoints, WebSocket, request routing
Core Services	Evaluation Engine, Subject Router, Image Processor, Ink Detector, Rubric Manager, QR Session Manager, PDF Generator, Storage Service	All business logic
External AI	Gemini 2.0 Flash, Gemini 2.5 Flash	Handwriting reading and answer evaluation
Storage	File System, Data Store	Images, PDFs, assignments, rubrics
2.2 Tech Stack
Component	Technology
Frontend	React 18+, TypeScript, Vite
Backend	Python 3.10, FastAPI, Uvicorn
AI Models	Gemini 2.0 Flash (eval), Gemini 2.5 Flash (math extraction)
Image Processing	OpenCV (cleanup), NumPy + Pillow (ink detection)
PDF Generation	ReportLab or WeasyPrint
Real-time	WebSocket (native FastAPI)
Storage	Local filesystem (swappable via abstraction)
Data	JSON files (swappable to database via abstraction)
3. User Flows
3.1 Teacher: Assignment Creation
Refer to: Diagram 2 — Teacher Assignment Flow

Flow:

Teacher opens "Create Assignment" — enters title, subject, grade level
Teacher chooses input method:
Type questions: Enters questions as text, optionally with expected answers
Upload image: Uploads photo/scan of question paper → Gemini extracts questions → Teacher confirms/edits extracted questions
System checks if expected answers are provided:
Yes: Rubric stored directly, assignment is ready
No: Gemini auto-generates expected answers → Teacher reviews
For diagram-based questions without teacher reference, system generates descriptive evaluation criteria and flags as "teacher review recommended"
Teacher approves, edits, or leaves for later review
Assignment becomes available to students immediately (students can attempt while teacher reviews auto-generated answers; final teacher evaluation happens after submission)
3.2 Student: Scanning & Evaluation
Refer to: Diagram 3 — Student Evaluation Flow

Flow:

Student opens assignment, clicks "Scan"
Platform detection:
Mobile: Camera opens directly via WebRTC
Desktop: QR code generated → Student scans with phone → Phone acts as camera only, images stream to desktop via WebSocket
Student scans pages one by one (manual capture per page)
On completion, all page images are processed:
Image cleanup: Perspective correction, contrast enhancement, shadow removal (OpenCV)
Store: Both raw and cleaned images saved
Evaluation runs (see Pipeline Design §4.1)
Results displayed in split view:
Left: Scanned page with color-coded highlighted answer regions (green/orange/red based on score)
Right: Per-question breakdown — extracted answer, score, feedback
Mobile: Stacked layout instead of side-by-side
Score check against 70% threshold:
≥ 70%: "Ready to submit" — smooth submission flow
< 70%: Warning with areas to improve + subtle hints (not exact answers) → Student can:
Rescan: Choose specific pages or full rescan → rewrite answers → rescan → re-evaluate
Submit anyway: Allowed, but warned
On submission: Generate PDF (cleaned pages + evaluation overlay + summary) → Submit to Classess
3.3 QR Code Scanning Flow
Participants: Desktop Browser, Backend Server, Phone Browser

Desktop requests QR session → Backend creates session with unique ID and expiry
Desktop displays QR code containing session URL
Student scans QR with phone → Opens lightweight scanning page
Phone connects to backend via WebSocket using session ID
Desktop receives "phone connected" notification
For each page: Phone captures image → Sends via WebSocket → Backend stores and forwards thumbnail to desktop
Phone signals "scanning complete" → Desktop receives all images → Evaluation begins
Results displayed on desktop only. Phone shows "Scanning complete, view results on your computer"
4. Core Pipeline Design
4.1 Evaluation Pipeline (Dual-Layer)
Refer to: Diagram 4 — Evaluation Pipeline

The pipeline uses subject-based routing to balance accuracy and speed.

text

Input: Cleaned page images + Rubric
                    │
                    ▼
            ┌───────────────┐
            │ Subject Router │
            └───────┬───────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   TEXT SUBJECTS            MATH SUBJECTS
        │                       │
        ▼                       ▼
  ┌──────────────┐      ┌──────────────────┐
  │ Gemini 2.0   │      │ Gemini 2.5 Flash │
  │ Flash        │      │ LAYER 1:         │
  │              │      │ Extract text     │
  │ Single call: │      │ (accurate        │
  │ Read image + │      │  reading)        │
  │ Evaluate     │      └────────┬─────────┘
  │              │               │
  │ ~3-4s        │               ▼
  └──────┬───────┘      ┌──────────────────┐
         │              │ Gemini 2.0 Flash │
         │              │ LAYER 2:         │
         │              │ Evaluate text    │
         │              │ against rubric   │
         │              │ (no image, fast) │
         │              │ ~2-3s            │
         │              └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
              PARALLEL TASK:
         ┌──────────────────┐
         │  Ink Detection   │
         │  (runs alongside │
         │   evaluation)    │
         │  ~100ms          │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  Region Mapper   │
         │  Match scores to │
         │  bounding boxes  │
         │  by vertical     │
         │  order           │
         └────────┬─────────┘
                  │
                  ▼
            Final Result JSON
Latency:

Text subjects: ~3-4 seconds
Math subjects: ~17-20 seconds (extraction) + ~2-3 seconds (evaluation) = ~19-23 seconds total, but Layer 1 and ink detection run in parallel
Key rule: Layer 2 for math receives ONLY extracted text, no image. This makes it a fast text-only reasoning call.

4.2 Image Processing Pipeline
Runs on every captured page before evaluation.

Step	Operation	Library
1	Convert to grayscale	OpenCV
2	Edge detection → find paper boundary	OpenCV (Canny)
3	Perspective correction → warp to rectangle	OpenCV (warpPerspective)
4	Adaptive contrast enhancement	OpenCV (CLAHE)
5	Shadow removal via local illumination normalization	OpenCV
6	Resize to standard dimensions	OpenCV
7	Save cleaned image	Pillow
Input: Raw camera photo (possibly angled, shadowed, uneven lighting)
Output: Clean, flat, high-contrast document image

4.3 Ink Detection Pipeline
Runs in parallel with Gemini evaluation. Finds WHERE answers are on the page without reading them.

Step	Operation
1	Convert cleaned image to grayscale
2	Gaussian blur to estimate local background
3	Subtract: pixels significantly darker than background = ink
4	Calculate row-by-row ink density
5	Smooth density curve, apply dynamic threshold
6	Find contiguous ink regions (answer bands)
7	Merge nearby regions, filter noise
8	Find horizontal extent per region
9	Output bounding boxes (normalized coordinates)
Input: Cleaned page image + expected number of answers
Output: List of bounding boxes, one per answer region

4.4 PDF Generation
Generated on submission for teacher review.

Page	Content
Cover	Student name, assignment title, date, total score
Per scanned page	Cleaned image with colored bounding box overlays showing scores
Summary	Per-question table: question text, extracted answer, score, feedback
Metadata	Prompt version, model used, evaluation timestamp, confidence
5. API Specification
5.1 Assignment Management
text

POST   /api/v1/assignments
       Body: { title, subject, grade_level, subject_type, questions[] }
       Response: { id, status: "created" }

POST   /api/v1/assignments/extract-questions
       Body: multipart { image }
       Response: { extracted_questions[], source_image_ref }

GET    /api/v1/assignments
       Response: { assignments[] }

GET    /api/v1/assignments/{id}
       Response: { full assignment with questions and answers }

PUT    /api/v1/assignments/{id}
       Body: { updated fields }

DELETE /api/v1/assignments/{id}

POST   /api/v1/assignments/{id}/generate-answers
       Response: { generated_answers[], status: "pending_approval" }

POST   /api/v1/assignments/{id}/approve-answers
       Body: { answers[] with optional edits }
       Response: { status: "approved" }
5.2 Evaluation
text

POST   /api/v1/prepare
       Body: { assignment_id, student_id }
       Response: { status, title, total_questions, total_marks,
                   answers_approved }

POST   /api/v1/evaluate
       Body: multipart { assignment_id, student_id,
                         images[] (one per page) }
       Response: {
           pages: [{
               page_number,
               cleaned_image_url,
               is_readable,
               is_relevant,
               questions: [{
                   q_number,
                   extracted_answer,
                   score,
                   max_marks,
                   feedback,
                   bounding_box: [y_min, x_min, y_max, x_max],
                   hints: (only if score < threshold)
               }]
           }],
           total_score,
           max_score,
           percentage,
           meets_threshold,
           overall_feedback,
           prompt_version,
           model_used,
           confidence
       }

POST   /api/v1/evaluate/rescan
       Body: multipart { assignment_id, student_id, 
                         submission_id, page_numbers[], images[] }
       Response: { updated evaluation result (same schema) }
5.3 QR Session
text

POST   /api/v1/qr-session
       Body: { assignment_id, student_id }
       Response: { session_id, qr_data, ws_url, expires_at }

GET    /api/v1/qr-session/{session_id}
       Response: { status, pages_received }

WebSocket  /ws/scan/{session_id}
           Phone connects here
           Phone sends: { type: "image", data: base64, page_num }
           Phone sends: { type: "complete" }

WebSocket  /ws/desktop/{session_id}
           Desktop connects here
           Receives: { type: "phone_connected" }
           Receives: { type: "page_received", page_num, thumbnail }
           Receives: { type: "scanning_complete", total_pages }
5.4 Submission
text

POST   /api/v1/submissions
       Body: { assignment_id, student_id, evaluation_id }
       Response: { submission_id, pdf_url, submitted_at }

GET    /api/v1/submissions/{id}
       Response: { full submission details }

GET    /api/v1/submissions/{id}/pdf
       Response: PDF file download
5.5 Health
text

GET    /api/v1/health
       Response: { status, gemini_reachable, storage_ok, version }
6. Data Models
6.1 Assignment
text

Assignment {
    id: string (uuid)
    title: string
    subject: string
    grade_level: integer
    subject_type: enum ["text", "math"]
    question_source: enum ["typed", "extracted_from_image"]
    source_image_ref: string? (if uploaded image)
    created_by: string (teacher_id)
    created_at: datetime
    updated_at: datetime
}
6.2 Question
text

Question {
    id: string (uuid)
    assignment_id: string (FK)
    q_number: integer
    text: string
    max_marks: integer
    has_diagram: boolean
    diagram_description: string? (for diagram-based evaluation)
    diagram_ref: string? (image reference if teacher provided)
}
6.3 Expected Answer
text

ExpectedAnswer {
    id: string (uuid)
    question_id: string (FK)
    answer_text: string
    is_auto_generated: boolean
    approved_by_teacher: boolean
    approved_at: datetime?
    teacher_notes: string? (edits/comments from teacher)
}
6.4 Evaluation
text

Evaluation {
    id: string (uuid)
    assignment_id: string (FK)
    student_id: string
    pages: PageScan[]
    results: QuestionResult[]
    total_score: float
    max_score: float
    percentage: float
    meets_threshold: boolean
    overall_feedback: string
    model_used: string
    prompt_version: string
    confidence: float
    evaluated_at: datetime
}
6.5 Page Scan
text

PageScan {
    page_number: integer
    raw_image_ref: string
    cleaned_image_ref: string
    is_readable: boolean
    is_relevant: boolean
}
6.6 Question Result
text

QuestionResult {
    q_number: integer
    page_number: integer
    extracted_answer: string
    score: float
    max_marks: float
    feedback: string
    hints: string? (subtle hints, not answers)
    bounding_box: [int, int, int, int]? (normalized 0-1000)
    mapping_confidence: float
}
6.7 QR Session
text

QRSession {
    session_id: string (uuid)
    assignment_id: string
    student_id: string
    status: enum ["waiting", "connected", "scanning", "complete", "expired"]
    pages_received: integer
    page_images: string[] (refs)
    created_at: datetime
    expires_at: datetime (created_at + 10 minutes)
}
6.8 Submission
text

Submission {
    id: string (uuid)
    evaluation_id: string (FK)
    assignment_id: string (FK)
    student_id: string
    pdf_ref: string
    total_score: float
    max_score: float
    percentage: float
    submitted_at: datetime
}
7. Component Architecture
7.1 Backend
text

app/
├── main.py                     FastAPI app, CORS, lifespan
├── config.py                   Environment-based configuration
│
├── api/
│   ├── routes/
│   │   ├── health.py           GET /health
│   │   ├── assignments.py      CRUD + extract + approve
│   │   ├── evaluate.py         POST /prepare, /evaluate, /evaluate/rescan
│   │   ├── qr_session.py       POST /qr-session, GET status
│   │   ├── submissions.py      POST /submit, GET, GET /pdf
│   │   └── websocket.py        WS /ws/scan/{id}, /ws/desktop/{id}
│   └── dependencies.py         Shared deps (auth, services)
│
├── core/
│   ├── evaluator.py            Orchestrates full evaluation pipeline
│   ├── subject_router.py       Routes text vs math to different pipelines
│   ├── text_evaluator.py       Single-call Gemini 2.0 (text subjects)
│   ├── math_evaluator.py       Dual-layer: 2.5 extract → 2.0 evaluate
│   ├── rubric.py               Rubric generation + caching
│   ├── ink_detector.py         Adaptive ink detection (NumPy)
│   ├── region_mapper.py        Maps scores → bounding boxes
│   ├── image_processor.py      OpenCV cleanup pipeline
│   ├── question_extractor.py   Extract questions from image (Gemini)
│   └── prompts/
│       ├── text_eval_v1.py     Prompt for text subjects
│       ├── math_extract_v1.py  Prompt for math extraction
│       ├── math_eval_v1.py     Prompt for math evaluation
│       ├── rubric_gen_v1.py    Prompt for answer generation
│       └── question_extract_v1.py  Prompt for question extraction
│
├── services/
│   ├── qr_session.py           QR session lifecycle management
│   ├── pdf_generator.py        PDF creation from evaluation results
│   └── submission.py           Submission creation and management
│
├── data/
│   ├── source.py               AssignmentDataSource protocol
│   ├── local_source.py         JSON file implementation
│   └── classess_source.py      Classess API implementation (stub)
│
├── storage/
│   ├── base.py                 StorageService protocol
│   └── local.py                Filesystem implementation
│
└── models/
    ├── assignment.py            Assignment, Question, ExpectedAnswer
    ├── evaluation.py            Evaluation, QuestionResult, PageScan
    ├── submission.py            Submission
    ├── qr_session.py            QRSession
    └── common.py                Shared types, enums
7.2 Frontend
text

src/
├── App.tsx                     Root: state machine (flow controller)
├── pages/
│   ├── StudentFlow.tsx         Student scanning + evaluation flow
│   └── TeacherFlow.tsx         Assignment creation + review flow
│
├── components/
│   ├── Scanner/
│   │   ├── CameraFeed.tsx      WebRTC camera + manual capture
│   │   ├── PageThumbnails.tsx  Preview of captured pages
│   │   └── ScanControls.tsx    Capture, retake, done buttons
│   │
│   ├── QRScanner/
│   │   ├── QRDisplay.tsx       Shows QR code on desktop
│   │   ├── PhoneScanPage.tsx   Lightweight page opened on phone
│   │   └── ConnectionStatus.tsx  Shows phone connected / pages received
│   │
│   ├── Results/
│   │   ├── SplitView.tsx       Left: image + boxes, Right: breakdown
│   │   ├── PageViewer.tsx      Scanned page with highlighted regions
│   │   ├── ScoreBreakdown.tsx  Per-question score + feedback
│   │   ├── ScoreWarning.tsx    Below threshold warning + hints
│   │   └── SubmitButton.tsx    Submit with confirmation
│   │
│   ├── Teacher/
│   │   ├── AssignmentForm.tsx  Create assignment (type or upload)
│   │   ├── QuestionEditor.tsx  Edit extracted/typed questions
│   │   ├── AnswerReview.tsx    Review auto-generated answers
│   │   └── ImageUpload.tsx     Upload question paper image
│   │
│   └── Common/
│       ├── Loading.tsx         Loading states with progress
│       └── ErrorBoundary.tsx   Error handling UI
│
├── hooks/
│   ├── useCamera.ts            Camera access + capture
│   ├── useWebSocket.ts         WebSocket connection management
│   ├── useEvaluation.ts        Evaluation API calls
│   └── useQRSession.ts         QR session lifecycle
│
├── services/
│   └── api.ts                  Backend API client (axios/fetch)
│
├── types/
│   └── index.ts                TypeScript interfaces
│
└── utils/
    └── postMessage.ts          Communication with host app (Classess)
8. Error Handling Strategy
Scenario	Detection	Handling	User Sees
Gemini API timeout	Request exceeds 30s	Retry once, then fail gracefully	"Evaluation taking longer than expected. Retry?"
Gemini returns invalid JSON	JSON parse fails	Retry once with same image	"Evaluation unclear. Retrying..."
Image too dark/blurry	Gemini flags is_readable: false	Return immediately, no evaluation	"Image is unclear. Please rescan this page."
Wrong assignment content	Gemini flags is_relevant: false	Return immediately	"This doesn't match the assignment. Check the right pages."
Ink detection finds 0 regions	No regions returned	Show results without bounding boxes	Results shown normally, no highlighting
Image cleanup fails	OpenCV exception	Skip cleanup, use raw image	Evaluation proceeds with raw image (may be less accurate)
QR session expired	Timestamp check	Close session, prompt new QR	"Session expired. Generate a new QR code."
Phone disconnects during scan	WebSocket close event	Desktop notified, can generate new QR	"Phone disconnected. Reconnect or generate new QR."
Math extraction returns garbage	Low confidence from Gemini	Flag in results	"Some answers could not be read clearly. Teacher will review."
PDF generation fails	Exception in generator	Store evaluation without PDF	"Results saved. PDF will be available shortly."
Principle: Never crash. Never lose data. Always show something useful. Bounding boxes are enhancement, not requirement.

9. Configuration
env

# ── AI Models ──
GEMINI_API_KEY=xxx
TEXT_EVAL_MODEL=gemini-2.0-flash
MATH_EXTRACT_MODEL=gemini-2.5-flash
MATH_EVAL_MODEL=gemini-2.0-flash
MODEL_TEMPERATURE=0
MAX_OUTPUT_TOKENS=4096

# ── Thresholds ──
SCORE_THRESHOLD_PERCENT=70
INK_SENSITIVITY=25
MIN_REGION_HEIGHT_RATIO=0.03

# ── Storage ──
STORAGE_TYPE=local
STORAGE_PATH=./data/images
DATA_SOURCE=local
DATA_PATH=./data/assignments

# ── QR Sessions ──
QR_SESSION_EXPIRY_MINUTES=10

# ── Server ──
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=["http://localhost:3000"]

# ── Feature Flags ──
ENABLE_IMAGE_CLEANUP=true
ENABLE_QR_SCANNING=true