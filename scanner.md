

# 📋 Complete Project Document: Assignment Submission System with Real-Time Camera Capture & CV Pipeline

## Smart Assignment Submission System — Technical Architecture & Implementation Document

---

## 1. EXECUTIVE SUMMARY

This document provides a comprehensive technical blueprint for building a **standalone Assignment Submission System** that allows students to scan a QR code from a web application, establish a real-time WebSocket connection with their mobile device, capture handwritten assignment pages via camera, process them through a Computer Vision pipeline, generate an enhanced PDF, and deliver it back for submission or storage.

The system is designed as a **standalone microservice** with clean API boundaries so it can be seamlessly integrated into any larger school management application.

---

## 2. SYSTEM OVERVIEW & HIGH-LEVEL FLOW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HIGH-LEVEL SYSTEM FLOW                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │ STEP 1   │───▶│ STEP 2   │───▶│ STEP 3   │───▶│ STEP 4           │  │
│  │ Click    │    │ QR Code  │    │ Choose   │    │ Open Camera      │  │
│  │ Submit   │    │ Scan or  │    │ Mode     │    │ Capture Pages    │  │
│  │ Button   │    │ Continue │    │          │    │                  │  │
│  └──────────┘    │ on Same  │    └──────────┘    └──────────────────┘  │
│                  │ Device   │                            │              │
│                  └──────────┘                            ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │ STEP 8   │◀───│ STEP 7   │◀───│ STEP 6   │◀───│ STEP 5           │  │
│  │ Upload   │    │ Deliver  │    │ CV       │    │ Click Finish     │  │
│  │ to DB /  │    │ PDF Back │    │ Pipeline │    │                  │  │
│  │ Share    │    │          │    │ Process  │    │                  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DETAILED STEP-BY-STEP FLOW

### Step 1: Assignment Submit Button
- Student navigates to the Assignments module in the school application.
- Clicks the **"Submit Assignment"** button.
- The backend generates a **unique session ID** (UUID v4) and a **short-lived JWT token** embedded in a QR code URL.

### Step 2: QR Code Display & Device Connection
- The web app displays:
  - A **QR Code** containing a URL like: `https://{domain}/capture/{session_id}?token={jwt_token}`
  - A **"Continue on this device"** button for users already on a capable device.
- **QR Code Scan Path**: User scans with mobile → opens URL in mobile browser → WebSocket handshake initiated.
- **Same Device Path**: User clicks continue → same browser opens the capture interface → WebSocket or internal event bus used.

### Step 3: Mode Confirmation
- On the capture device, user sees a confirmation screen:
  - Session details (assignment name, subject)
  - **"Start Camera Capture"** button
  - Device compatibility check (camera permissions, browser support)

### Step 4: Camera Opens & Page Capture
- Camera opens using the **MediaDevices API** (`getUserMedia`).
- User shows pages of their handwritten copy one by one.
- For each page:
  - Live preview with **edge detection overlay** (guides the user to align the page).
  - User taps **"Capture"** or system **auto-captures** when a stable document is detected.
  - Captured image is sent via **WebSocket as binary frame** (or chunked base64) to the backend.
  - A thumbnail confirmation appears on screen.
- User can **re-capture** any page or **reorder** pages.

### Step 5: Finish Capture
- User clicks **"Finish"** button.
- A final confirmation shows all captured page thumbnails.
- User confirms → a "Processing..." state is shown.
- The backend is notified that all pages for this session are complete.

### Step 6: CV Pipeline Processing
The server-side pipeline processes all captured images:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CV PIPELINE ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Raw Image                                                              │
│      │                                                                  │
│      ▼                                                                  │
│  ┌──────────────────────┐                                              │
│  │ 1. DOCUMENT DETECTION│  ── Contour detection, find paper edges      │
│  │    & PERSPECTIVE     │  ── Four-point perspective transform         │
│  │    CORRECTION        │  ── Crop to document boundaries              │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 2. SHADOW REMOVAL    │  ── Gaussian blur background estimation      │
│  │                      │  ── Divide original by background            │
│  │                      │  ── Normalize result                         │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 3. LIGHTING &        │  ── CLAHE (Adaptive Histogram Equalization)  │
│  │    CONTRAST          │  ── White balance correction                  │
│  │    NORMALIZATION     │  ── Brightness normalization                  │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 4. NOISE REDUCTION   │  ── Non-local means denoising               │
│  │    & SHARPENING      │  ── Unsharp masking                          │
│  │                      │  ── Bilateral filtering                      │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 5. BINARIZATION      │  ── Adaptive thresholding (Sauvola/Niblack) │
│  │    (OPTIONAL -       │  ── For pure text pages                      │
│  │     CONTENT-AWARE)   │  ── Skip for diagram-heavy pages            │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 6. DIAGRAM/TEXT      │  ── Classify regions as text vs diagram      │
│  │    DETECTION &       │  ── Preserve diagram regions in grayscale    │
│  │    PRESERVATION      │  ── Enhance text regions separately          │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 7. DPI NORMALIZATION │  ── Resize to consistent 300 DPI            │
│  │    & ORIENTATION     │  ── Auto-rotate if needed                    │
│  │    CORRECTION        │  ── Deskewing                                │
│  └──────────┬───────────┘                                              │
│             ▼                                                           │
│  ┌──────────────────────┐                                              │
│  │ 8. PDF GENERATION    │  ── Compile all processed pages             │
│  │                      │  ── Optimize file size                       │
│  │                      │  ── Add metadata                             │
│  └──────────────────────┘                                              │
│             │                                                           │
│             ▼                                                           │
│        Enhanced PDF                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Step 7: PDF Delivery
- **If scanned via mobile**: PDF is sent back through the WebSocket connection to the web app on the original device. The mobile shows "Submission Complete."
- **If same device**: PDF is available directly in the browser for preview/download.
- Real-time progress updates via WebSocket during processing.

### Step 8: Upload & Share
- PDF is stored in the backend (filesystem / object storage).
- API endpoints available for:
  - Uploading to database
  - Sharing via email
  - Downloading
  - Integration with the larger school application

---

## 4. TECHNOLOGY STACK

| Layer | Technology | Justification |
|-------|-----------|---------------|
| **Backend Framework** | FastAPI (Python 3.11+) | Async-native, WebSocket support, auto-generated docs, high performance |
| **WebSocket** | FastAPI WebSocket + `uvicorn` | Native support, async, low latency |
| **Task Queue** | Celery + Redis | Offload heavy CV processing, prevent blocking |
| **CV Processing** | OpenCV 4.x + NumPy + scikit-image | Industry standard, extensive document processing capabilities |
| **Diagram Detection** | YOLOv8-nano or custom CNN classifier | Lightweight, fast inference for text vs diagram classification |
| **PDF Generation** | `img2pdf` + `pikepdf` (or `reportlab`) | Lossless image-to-PDF, metadata support, small file sizes |
| **OCR (Optional)** | Tesseract via `pytesseract` or `EasyOCR` | Create searchable PDF layer |
| **QR Code Generation** | `qrcode` Python library | Lightweight, fast |
| **Frontend (Capture UI)** | Vanilla JS / Lightweight Preact | Minimal bundle, fast load on mobile, no heavy framework needed |
| **Camera API** | MediaDevices API (`getUserMedia`) | Native browser API, no plugins needed |
| **Edge Detection UI** | `OpenCV.js` (optional) or server-side | Client-side document boundary preview |
| **Database** | PostgreSQL + SQLAlchemy (async) | Reliable, async driver available (`asyncpg`) |
| **File Storage** | MinIO (S3-compatible) or local filesystem | Scalable, S3-compatible API for easy migration |
| **Caching** | Redis | Session management, WebSocket pub/sub, rate limiting |
| **Containerization** | Docker + Docker Compose | Reproducible environments |
| **Reverse Proxy** | Nginx | SSL termination, WebSocket proxying, static file serving |
| **Security** | JWT (PyJWT), HTTPS, CORS | Session tokens, encrypted transport |

---

## 5. ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SYSTEM ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐         ┌─────────────┐                                   │
│  │   DESKTOP   │         │   MOBILE    │                                   │
│  │   BROWSER   │         │   BROWSER   │                                   │
│  │             │         │             │                                   │
│  │ ┌─────────┐ │         │ ┌─────────┐ │                                   │
│  │ │Assignment│ │         │ │ Camera  │ │                                   │
│  │ │  Module  │ │         │ │ Capture │ │                                   │
│  │ │         │ │         │ │   UI    │ │                                   │
│  │ │ QR Code │ │         │ │         │ │                                   │
│  │ │ Display │ │         │ │  WebRTC │ │                                   │
│  │ └────┬────┘ │         │ └────┬────┘ │                                   │
│  └──────┼──────┘         └──────┼──────┘                                   │
│         │    WebSocket          │   WebSocket                               │
│         │    (wss://)           │   (wss://) + Binary frames               │
│         └──────────┬────────────┘                                          │
│                    ▼                                                        │
│  ┌─────────────────────────────────────────┐                               │
│  │              NGINX                       │                               │
│  │   (SSL Termination, WS Proxy, Static)   │                               │
│  └────────────────┬────────────────────────┘                               │
│                   ▼                                                         │
│  ┌─────────────────────────────────────────┐                               │
│  │          FASTAPI APPLICATION             │                               │
│  │                                          │                               │
│  │  ┌──────────┐  ┌──────────┐  ┌────────┐ │    ┌──────────────────────┐  │
│  │  │ REST API │  │WebSocket │  │Session │ │    │                      │  │
│  │  │Endpoints │  │ Manager  │  │Manager │ │───▶│       REDIS          │  │
│  │  │          │  │          │  │        │ │    │  (Sessions, PubSub,  │  │
│  │  └──────────┘  └──────────┘  └────────┘ │    │   Task Queue Broker) │  │
│  │                                          │    └──────────────────────┘  │
│  │  ┌──────────────────────────────────┐   │              │               │
│  │  │       SESSION COORDINATOR        │   │              ▼               │
│  │  │  (Pairs desktop ↔ mobile)        │   │    ┌──────────────────────┐  │
│  │  └──────────────────────────────────┘   │    │    CELERY WORKERS    │  │
│  │                                          │    │                      │  │
│  └──────────────────┬──────────────────────┘    │  ┌────────────────┐  │  │
│                     │                            │  │  CV PIPELINE   │  │  │
│                     ▼                            │  │                │  │  │
│  ┌──────────────────────────────┐               │  │ • Doc Detection│  │  │
│  │        POSTGRESQL            │               │  │ • Shadow Rem.  │  │  │
│  │                              │               │  │ • Enhancement  │  │  │
│  │  • Sessions                  │               │  │ • Diagram Det. │  │  │
│  │  • Assignments               │               │  │ • PDF Gen.     │  │  │
│  │  • Submissions               │               │  │                │  │  │
│  │  • Users (minimal)           │               │  └────────────────┘  │  │
│  └──────────────────────────────┘               │                      │  │
│                                                  └──────────┬───────────┘  │
│                                                             │              │
│                                                             ▼              │
│                                                  ┌──────────────────────┐  │
│                                                  │   FILE STORAGE       │  │
│                                                  │   (MinIO / Local)    │  │
│                                                  │                      │  │
│                                                  │  • Raw images        │  │
│                                                  │  • Processed images  │  │
│                                                  │  • Generated PDFs    │  │
│                                                  └──────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. WEBSOCKET COMMUNICATION PROTOCOL

### 6.1 Connection Establishment

```
┌──────────┐                ┌──────────┐               ┌──────────┐
│ DESKTOP  │                │  SERVER  │               │  MOBILE  │
│ BROWSER  │                │          │               │  BROWSER │
└────┬─────┘                └────┬─────┘               └────┬─────┘
     │                           │                          │
     │  1. POST /session/create  │                          │
     │  ─────────────────────▶  │                          │
     │                           │                          │
     │  2. {session_id, qr_url,  │                          │
     │      ws_token}            │                          │
     │  ◀─────────────────────  │                          │
     │                           │                          │
     │  3. WS Connect            │                          │
     │     /ws/desktop/{sid}     │                          │
     │  ─────────────────────▶  │                          │
     │                           │                          │
     │     [QR Code displayed]   │                          │
     │                           │                          │
     │                           │  4. User scans QR code   │
     │                           │  ◀────────────────────  │
     │                           │                          │
     │                           │  5. GET /capture/{sid}   │
     │                           │  ◀────────────────────  │
     │                           │                          │
     │                           │  6. Serve capture page   │
     │                           │  ────────────────────▶  │
     │                           │                          │
     │                           │  7. WS Connect           │
     │                           │     /ws/mobile/{sid}     │
     │                           │  ◀────────────────────  │
     │                           │                          │
     │  8. {type: "device_paired"│                          │
     │      device_info: {...}}  │                          │
     │  ◀─────────────────────  │                          │
     │                           │                          │
```

### 6.2 Message Protocol (JSON)

All WebSocket messages follow this envelope format:

```json
{
  "type": "message_type",
  "timestamp": "ISO-8601",
  "session_id": "uuid",
  "payload": { }
}
```

**Message Types:**

| Type | Direction | Description |
|------|-----------|-------------|
| `device_paired` | Server → Desktop | Mobile device connected successfully |
| `capture_started` | Mobile → Server → Desktop | Camera opened, capture session begun |
| `image_captured` | Mobile → Server | Raw image binary frame sent |
| `image_received` | Server → Mobile | Acknowledgment with thumbnail |
| `capture_progress` | Server → Desktop | Page count update, thumbnails |
| `capture_finished` | Mobile → Server | User clicked Finish |
| `processing_started` | Server → Both | CV pipeline started |
| `processing_progress` | Server → Both | Progress percentage + current step |
| `processing_complete` | Server → Both | PDF ready, download URL |
| `error` | Server → Both | Error details |
| `session_expired` | Server → Both | Session timeout |
| `heartbeat` | Both → Server | Keep-alive ping every 15s |

### 6.3 Binary Frame Protocol for Images

To minimize latency, images are sent as **binary WebSocket frames** with a small header:

```
┌──────────────────────────────────────────────────┐
│            BINARY FRAME STRUCTURE                │
├──────────────────────────────────────────────────┤
│                                                   │
│  Bytes 0-3:    Magic number (0x494D4731 = "IMG1") │
│  Bytes 4-5:    Page number (uint16, big-endian)   │
│  Bytes 6-9:    Total size (uint32, big-endian)    │
│  Bytes 10-11:  Chunk index (uint16)               │
│  Bytes 12-13:  Total chunks (uint16)              │
│  Bytes 14-15:  Flags (compression, format)        │
│  Bytes 16+:    Image data (JPEG compressed)       │
│                                                   │
└──────────────────────────────────────────────────┘
```

**Why JPEG over WebSocket?**
- Client-side `<canvas>.toBlob('image/jpeg', 0.92)` compresses 4K camera frames to ~500KB-1MB.
- Binary frames avoid base64 overhead (33% size increase).
- Chunking handles images larger than WebSocket frame limits.

---

## 7. DETAILED CV PIPELINE SPECIFICATION

### 7.1 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CV PIPELINE DETAIL                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  INPUT: Raw camera image (JPEG, ~2-4K resolution)                   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 1: PREPROCESSING                                   │        │
│  │                                                           │        │
│  │  1a. Decode JPEG → NumPy array (BGR)                     │        │
│  │  1b. Resize if > 4000px on any side (preserve ratio)     │        │
│  │  1c. Convert to grayscale for analysis                    │        │
│  │  1d. Blur detection (Laplacian variance)                  │        │
│  │      → If blurry, flag for user notification              │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 2: DOCUMENT DETECTION & PERSPECTIVE CORRECTION     │        │
│  │                                                           │        │
│  │  2a. Apply Gaussian blur (5x5) to reduce noise           │        │
│  │  2b. Canny edge detection                                 │        │
│  │  2c. Find contours, select largest quadrilateral          │        │
│  │  2d. If no quad found → use full image with padding crop │        │
│  │  2e. Order corner points (top-left, top-right,           │        │
│  │      bottom-right, bottom-left)                           │        │
│  │  2f. Compute perspective transform matrix                 │        │
│  │  2g. Apply warpPerspective → bird's-eye view             │        │
│  │  2h. Auto-determine output size from aspect ratio         │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 3: ORIENTATION & DESKEW                             │        │
│  │                                                           │        │
│  │  3a. Detect text orientation using Tesseract OSD           │        │
│  │      or Hough line transform                               │        │
│  │  3b. Auto-rotate (0°, 90°, 180°, 270°)                   │        │
│  │  3c. Fine deskew using Hough lines on text                │        │
│  │      → Rotate by detected skew angle                      │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 4: SHADOW REMOVAL                                   │        │
│  │                                                           │        │
│  │  Method: Background estimation via morphological ops      │        │
│  │                                                           │        │
│  │  4a. Convert to grayscale                                 │        │
│  │  4b. Apply large morphological closing (kernel ~21x21)    │        │
│  │      → This estimates the background/shadow pattern       │        │
│  │  4c. Divide original grayscale by background estimate     │        │
│  │  4d. Normalize to 0-255 range                             │        │
│  │  4e. Apply gamma correction if needed                     │        │
│  │                                                           │        │
│  │  Alternative for complex shadows:                         │        │
│  │  → Use plane-fitting shadow removal                       │        │
│  │  → Estimate illumination plane, subtract                  │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 5: CONTRAST & BRIGHTNESS ENHANCEMENT               │        │
│  │                                                           │        │
│  │  5a. CLAHE (Clip Limit Adaptive Histogram Equalization)   │        │
│  │      clipLimit=2.0, tileGridSize=(8,8)                    │        │
│  │  5b. White balance → make paper appear white              │        │
│  │      → Detect paper color, shift to pure white            │        │
│  │  5c. Contrast stretching (percentile-based)               │        │
│  │      → Map 5th percentile to 0, 95th to 255              │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 6: CONTENT-AWARE REGION CLASSIFICATION             │        │
│  │                                                           │        │
│  │  6a. Segment page into blocks/regions                     │        │
│  │  6b. Classify each region:                                │        │
│  │      → TEXT: Dense horizontal strokes                     │        │
│  │      → DIAGRAM: Connected shapes, curves, isolated marks │        │
│  │      → BLANK: No significant content                      │        │
│  │  6c. Store region masks for differential processing       │        │
│  │                                                           │        │
│  │  Classification method:                                    │        │
│  │  → Connected component analysis                           │        │
│  │  → Stroke width transform                                 │        │
│  │  → Aspect ratio & density heuristics                      │        │
│  │  → Optional: Lightweight CNN classifier (MobileNetV3)     │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 7: DIFFERENTIAL ENHANCEMENT                         │        │
│  │                                                           │        │
│  │  FOR TEXT REGIONS:                                        │        │
│  │  7a. Aggressive noise reduction (bilateral filter)        │        │
│  │  7b. Sauvola adaptive thresholding                        │        │
│  │      → Window size 25, k=0.2                              │        │
│  │  7c. Morphological cleanup (small opening)                │        │
│  │  7d. Output: Clean black text on white background         │        │
│  │                                                           │        │
│  │  FOR DIAGRAM REGIONS:                                     │        │
│  │  7e. Gentle denoising (non-local means, h=5)             │        │
│  │  7f. Edge preservation sharpening (unsharp mask)          │        │
│  │  7g. Maintain grayscale / color information               │        │
│  │  7h. Enhance line visibility                              │        │
│  │  7i. Output: Clean grayscale/color with clear lines       │        │
│  │                                                           │        │
│  │  COMPOSITE:                                               │        │
│  │  7j. Merge text & diagram regions using masks             │        │
│  │  7k. Smooth transitions at region boundaries              │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 8: FINAL CLEANUP & NORMALIZATION                    │        │
│  │                                                           │        │
│  │  8a. Resize to A4 dimensions at 300 DPI                   │        │
│  │      (2480 x 3508 pixels)                                 │        │
│  │  8b. Add thin white border/margin                         │        │
│  │  8c. Final sharpening pass (very gentle)                  │        │
│  │  8d. Convert to 8-bit grayscale or RGB                    │        │
│  │  8e. Compress as high-quality JPEG or PNG                 │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ STAGE 9: PDF GENERATION                                   │        │
│  │                                                           │        │
│  │  9a. Collect all processed page images in order           │        │
│  │  9b. Generate PDF using img2pdf (lossless embedding)      │        │
│  │  9c. Add metadata:                                        │        │
│  │      → Title: "{Student} - {Assignment} - {Date}"        │        │
│  │      → Author, Subject, Creation date                     │        │
│  │  9d. Optional: Run Tesseract OCR → invisible text layer  │        │
│  │      → Makes PDF searchable                               │        │
│  │  9e. Optimize PDF size (pikepdf linearization)            │        │
│  │  9f. Output: Final PDF file                               │        │
│  └─────────────────────────────────────────────────────────┘        │
│                                                                      │
│  OUTPUT: Enhanced PDF (300 DPI, shadow-free, clean text,            │
│          preserved diagrams, searchable, optimized size)             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 Specific Algorithm Parameters & Choices

| Stage | Algorithm | Key Parameters | Rationale |
|-------|-----------|---------------|-----------|
| Document Detection | Canny + Contour | threshold1=50, threshold2=150, epsilon=0.02*perimeter | Robust edge detection for paper boundaries |
| Shadow Removal | Morphological closing + Division | kernel=21x21, MORPH_CLOSE | Fast, effective for uniform & gradient shadows |
| Contrast Enhancement | CLAHE | clipLimit=2.0, grid=(8,8) | Local contrast without global over-saturation |
| Text Binarization | Sauvola Thresholding | window=25, k=0.2 | Superior to Otsu for uneven illumination |
| Noise Reduction (text) | Bilateral Filter | d=9, sigmaColor=75, sigmaSpace=75 | Preserves edges while smoothing noise |
| Noise Reduction (diagram) | Non-local Means | h=5, templateWindowSize=7, searchWindowSize=21 | Better detail preservation |
| Deskew | Hough Line Transform | threshold=100, minLineLength=100 | Accurate angle detection from text lines |
| Sharpening | Unsharp Mask | sigma=1.0, strength=0.5 | Gentle enhancement without artifacts |
| PDF Compression | JPEG in PDF | quality=92 for diagrams, quality=85 for text | Balance quality vs file size |

### 7.3 Diagram Detection Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│               DIAGRAM vs TEXT CLASSIFICATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Divide page into grid blocks (e.g., 8x8 grid)         │
│                                                                  │
│  Step 2: For each block, compute features:                      │
│   ┌───────────────────────────────────────────────────┐         │
│   │ Feature              │ Text Indicator │ Diagram   │         │
│   ├───────────────────────┼────────────────┼───────────┤         │
│   │ Stroke Width Variance │ Low            │ High      │         │
│   │ Horizontal projection │ Periodic peaks │ Irregular │         │
│   │ Connected component   │ Small, many    │ Large, few│         │
│   │   sizes               │                │           │         │
│   │ Aspect ratios of CCs  │ Wide rectangles│ Varied    │         │
│   │ Edge direction        │ Mostly horiz.  │ All dirs  │         │
│   │   histogram           │                │           │         │
│   │ Density (ink/area)    │ Moderate       │ Low-High  │         │
│   └───────────────────────┴────────────────┴───────────┘         │
│                                                                  │
│  Step 3: Classify each block using decision tree / threshold     │
│                                                                  │
│  Step 4: Merge adjacent diagram blocks into diagram regions      │
│                                                                  │
│  Step 5: Expand diagram regions by small margin                  │
│                                                                  │
│  Step 6: Create binary masks for text and diagram zones          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. API SPECIFICATION

### 8.1 REST Endpoints

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          REST API ENDPOINTS                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SESSION MANAGEMENT                                                     │
│  ──────────────────                                                     │
│                                                                         │
│  POST   /api/v1/sessions                                               │
│         → Create new capture session                                    │
│         → Body: { assignment_id, user_id }                              │
│         → Returns: { session_id, qr_code_url, qr_code_base64,         │
│                       ws_token, expires_at }                            │
│                                                                         │
│  GET    /api/v1/sessions/{session_id}                                  │
│         → Get session status and details                                │
│         → Returns: { status, page_count, created_at, ... }             │
│                                                                         │
│  DELETE /api/v1/sessions/{session_id}                                  │
│         → Cancel/cleanup a session                                      │
│                                                                         │
│  CAPTURE PAGE                                                           │
│  ────────────                                                           │
│                                                                         │
│  GET    /capture/{session_id}?token={jwt}                              │
│         → Serve the mobile capture UI HTML page                         │
│         → Token validated, session checked                              │
│                                                                         │
│  SUBMISSION / PDF                                                       │
│  ────────────────                                                       │
│                                                                         │
│  GET    /api/v1/submissions/{session_id}/pdf                           │
│         → Download the generated PDF                                    │
│         → Returns: PDF file stream                                      │
│                                                                         │
│  GET    /api/v1/submissions/{session_id}/status                        │
│         → Check processing status                                       │
│         → Returns: { status, progress_percent, current_step }          │
│                                                                         │
│  POST   /api/v1/submissions/{session_id}/upload                        │
│         → Upload PDF to permanent storage / database                    │
│         → Body: { destination: "db" | "s3", metadata: {...} }          │
│         → Returns: { upload_id, url }                                   │
│                                                                         │
│  POST   /api/v1/submissions/{session_id}/share                         │
│         → Share PDF via email or generate share link                    │
│         → Body: { method: "email" | "link", recipients: [...] }       │
│         → Returns: { share_url } or { email_status }                   │
│                                                                         │
│  INTEGRATION ENDPOINTS (for parent application)                        │
│  ──────────────────────────────────────────────                        │
│                                                                         │
│  POST   /api/v1/submit-assignment                                      │
│         → Full flow: accept PDF + metadata, store, return reference    │
│         → Body: multipart (pdf file + JSON metadata)                   │
│         → Returns: { submission_id, pdf_url, status }                  │
│                                                                         │
│  GET    /api/v1/submissions                                            │
│         → List submissions (with filters)                               │
│         → Query: ?user_id=&assignment_id=&status=&page=&limit=        │
│                                                                         │
│  GET    /api/v1/health                                                 │
│         → Service health check                                          │
│         → Returns: { status, version, uptime, dependencies }           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 WebSocket Endpoints

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       WEBSOCKET ENDPOINTS                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  WS  /ws/desktop/{session_id}?token={jwt}                              │
│      → Desktop browser connects here                                    │
│      → Receives: pairing status, progress updates, completion          │
│                                                                         │
│  WS  /ws/mobile/{session_id}?token={jwt}                               │
│      → Mobile browser connects here after QR scan                      │
│      → Sends: captured image binary frames                              │
│      → Receives: acknowledgments, processing results                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 9. DATABASE SCHEMA

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATABASE SCHEMA                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────┐                          │
│  │          capture_sessions                 │                          │
│  ├──────────────────────────────────────────┤                          │
│  │ id              UUID PRIMARY KEY          │                          │
│  │ assignment_id   VARCHAR(255) NOT NULL     │                          │
│  │ user_id         VARCHAR(255) NOT NULL     │                          │
│  │ status          ENUM('created',           │                          │
│  │                      'paired',            │                          │
│  │                      'capturing',         │                          │
│  │                      'processing',        │                          │
│  │                      'completed',         │                          │
│  │                      'failed',            │                          │
│  │                      'expired')           │                          │
│  │ device_info     JSONB                     │                          │
│  │ token_hash      VARCHAR(64)               │                          │
│  │ page_count      INTEGER DEFAULT 0         │                          │
│  │ pdf_path        VARCHAR(500)              │                          │
│  │ pdf_size_bytes  BIGINT                    │                          │
│  │ created_at      TIMESTAMP WITH TZ         │                          │
│  │ paired_at       TIMESTAMP WITH TZ         │                          │
│  │ completed_at    TIMESTAMP WITH TZ         │                          │
│  │ expires_at      TIMESTAMP WITH TZ         │                          │
│  └──────────────────┬───────────────────────┘                          │
│                     │ 1                                                  │
│                     │                                                    │
│                     │ N                                                  │
│  ┌──────────────────┴───────────────────────┐                          │
│  │          captured_pages                   │                          │
│  ├──────────────────────────────────────────┤                          │
│  │ id              UUID PRIMARY KEY          │                          │
│  │ session_id      UUID FK → capture_sessions│                          │
│  │ page_number     INTEGER NOT NULL          │                          │
│  │ raw_image_path  VARCHAR(500)              │                          │
│  │ processed_path  VARCHAR(500)              │                          │
│  │ image_size_bytes BIGINT                   │                          │
│  │ has_diagram     BOOLEAN DEFAULT FALSE     │                          │
│  │ blur_score      FLOAT                     │                          │
│  │ processing_time_ms INTEGER                │                          │
│  │ created_at      TIMESTAMP WITH TZ         │                          │
│  └──────────────────────────────────────────┘                          │
│                                                                         │
│  ┌──────────────────────────────────────────┐                          │
│  │          submissions                      │                          │
│  ├──────────────────────────────────────────┤                          │
│  │ id              UUID PRIMARY KEY          │                          │
│  │ session_id      UUID FK → capture_sessions│                          │
│  │ assignment_id   VARCHAR(255) NOT NULL     │                          │
│  │ user_id         VARCHAR(255) NOT NULL     │                          │
│  │ pdf_url         VARCHAR(500)              │                          │
│  │ pdf_hash        VARCHAR(64)               │ ← SHA-256               │
│  │ status          ENUM('pending',           │                          │
│  │                      'uploaded',          │                          │
│  │                      'shared',            │                          │
│  │                      'confirmed')         │                          │
│  │ uploaded_to     VARCHAR(100)              │                          │
│  │ metadata        JSONB                     │                          │
│  │ created_at      TIMESTAMP WITH TZ         │                          │
│  └──────────────────────────────────────────┘                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 10. SECURITY ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       SECURITY MEASURES                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 1. TRANSPORT SECURITY                                    │           │
│  │                                                           │           │
│  │  • All connections over HTTPS/WSS (TLS 1.3)             │           │
│  │  • Nginx handles SSL termination                         │           │
│  │  • HSTS headers enabled                                  │           │
│  │  • Certificate pinning for mobile capture page           │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 2. SESSION SECURITY                                      │           │
│  │                                                           │           │
│  │  • Session IDs: UUID v4 (non-guessable)                 │           │
│  │  • JWT tokens: Short-lived (15 minutes)                  │           │
│  │    → Contains: session_id, user_id, role, exp            │           │
│  │    → Signed with HS256 using server secret               │           │
│  │  • Token in QR code URL → single-use, validated once    │           │
│  │  • Session expiry: Auto-cleanup after 30 minutes        │           │
│  │  • One mobile connection per session (reject duplicates) │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 3. INPUT VALIDATION & SANITIZATION                       │           │
│  │                                                           │           │
│  │  • Max image size: 10MB per frame                        │           │
│  │  • Max pages per session: 50                             │           │
│  │  • File type validation (JPEG magic bytes check)        │           │
│  │  • Image dimension limits: max 5000x5000                │           │
│  │  • Rate limiting: max 2 images/second per session       │           │
│  │  • WebSocket message size limit: 15MB                    │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 4. API SECURITY                                          │           │
│  │                                                           │           │
│  │  • API key authentication for integration endpoints     │           │
│  │  • CORS: Whitelist specific origins only                 │           │
│  │  • Rate limiting: 100 requests/minute per IP             │           │
│  │  • Request size limits                                    │           │
│  │  • Input validation with Pydantic models                 │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 5. FILE STORAGE SECURITY                                 │           │
│  │                                                           │           │
│  │  • Files stored with UUID names (no user input in paths)│           │
│  │  • Separate directories per session                      │           │
│  │  • PDF download URLs: Signed URLs with expiry            │           │
│  │  • Auto-cleanup: Delete raw images after PDF generation  │           │
│  │  • File integrity: SHA-256 hash stored in DB             │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ 6. WEBSOCKET SECURITY                                    │           │
│  │                                                           │           │
│  │  • Token validation on connection handshake              │           │
│  │  • Heartbeat monitoring (disconnect after 30s silence)   │           │
│  │  • Message type whitelisting                              │           │
│  │  • Connection count limits per IP                         │           │
│  │  • Binary frame validation (magic number check)          │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 11. LATENCY OPTIMIZATION STRATEGY

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   LATENCY OPTIMIZATION MEASURES                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  NETWORK LAYER                                                          │
│  ─────────────                                                          │
│  • WebSocket (persistent connection) → No HTTP overhead per image      │
│  • Binary frames → No base64 encoding overhead (saves 33%)             │
│  • Client-side JPEG compression → Reduce transfer size 10x             │
│  • Connection keep-alive → No re-handshake                              │
│  • HTTP/2 for REST endpoints                                            │
│                                                                         │
│  APPLICATION LAYER                                                      │
│  ─────────────────                                                      │
│  • FastAPI async handlers → Non-blocking I/O                           │
│  • uvicorn with uvloop → Fastest Python event loop                     │
│  • Async file I/O → aiofiles for disk operations                       │
│  • Connection pooling → asyncpg for database                           │
│  • Redis pub/sub for cross-connection messaging                         │
│                                                                         │
│  PROCESSING LAYER                                                       │
│  ────────────────                                                       │
│  • Celery workers → Offload CV processing from API server              │
│  • NumPy vectorized operations → Avoid Python loops                    │
│  • OpenCV optimized builds (with TBB/OpenMP)                            │
│  • Pipeline parallelism → Process page N while capturing N+1           │
│  • Lazy loading → Only import heavy libraries in workers               │
│  • Image resize before processing → Work on optimal resolution         │
│  • Batch PDF generation → Generate once after all pages processed      │
│                                                                         │
│  INFRASTRUCTURE LAYER                                                   │
│  ────────────────────                                                   │
│  • Nginx buffering tuned for WebSocket                                  │
│  • Redis on same machine → Minimal broker latency                      │
│  • SSD storage → Fast image read/write                                  │
│  • Docker with volume mounts → Avoid overlay FS overhead               │
│                                                                         │
│  EXPECTED LATENCIES                                                     │
│  ─────────────────                                                      │
│  • QR scan → WS connection: < 500ms                                    │
│  • Image capture → server receipt: 200-800ms (depends on network)      │
│  • Single page CV processing: 500-1500ms                               │
│  • Full 10-page pipeline: 8-15 seconds                                  │
│  • PDF generation: 200-500ms                                            │
│  • PDF delivery back to client: 500-2000ms                              │
│  • Total (10 pages): ~15-25 seconds after finish click                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 12. PROJECT STRUCTURE

```
assignment-capture-service/
│
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.worker
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── alembic.ini
│
├── alembic/
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app initialization
│   ├── config.py                    # Settings (pydantic-settings)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py           # Main API router
│   │   │   ├── sessions.py         # Session endpoints
│   │   │   ├── submissions.py      # Submission/PDF endpoints
│   │   │   └── health.py           # Health check
│   │   └── dependencies.py         # Auth, rate limiting deps
│   │
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── manager.py              # WebSocket connection manager
│   │   ├── desktop_handler.py      # Desktop WS logic
│   │   ├── mobile_handler.py       # Mobile WS logic
│   │   └── protocol.py             # Message types, serialization
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── session_service.py      # Session business logic
│   │   ├── qr_service.py           # QR code generation
│   │   ├── pdf_service.py          # PDF generation
│   │   ├── storage_service.py      # File storage abstraction
│   │   └── share_service.py        # Email/link sharing
│   │
│   ├── cv_pipeline/
│   │   ├── __init__.py
│   │   ├── pipeline.py             # Main pipeline orchestrator
│   │   ├── document_detector.py    # Stage 2: Doc detection
│   │   ├── orientation.py          # Stage 3: Deskew/rotate
│   │   ├── shadow_removal.py       # Stage 4: Shadow removal
│   │   ├── enhancement.py          # Stage 5: Contrast/brightness
│   │   ├── region_classifier.py    # Stage 6: Text vs diagram
│   │   ├── text_enhancer.py        # Stage 7a: Text processing
│   │   ├── diagram_enhancer.py     # Stage 7b: Diagram processing
│   │   ├── compositor.py           # Stage 7c: Region merging
│   │   └── utils.py                # Shared CV utilities
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py           # Celery configuration
│   │   └── tasks.py                # Celery tasks
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py             # DB engine, session
│   │   ├── session.py              # CaptureSession model
│   │   ├── page.py                 # CapturedPage model
│   │   └── submission.py           # Submission model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── session.py              # Pydantic schemas
│   │   ├── submission.py
│   │   └── websocket.py            # WS message schemas
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── jwt_handler.py          # JWT creation/validation
│   │   ├── api_key.py              # API key auth
│   │   └── rate_limiter.py         # Rate limiting
│   │
│   └── static/
│       └── capture/
│           ├── index.html           # Mobile capture UI
│           ├── capture.js           # Camera + WS logic
│           └── styles.css           # Minimal styling
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api/
│   ├── test_websocket/
│   ├── test_cv_pipeline/
│   └── test_integration/
│
└── scripts/
    ├── setup_db.py
    └── cleanup_expired.py
```

---

## 13. FRONTEND CAPTURE UI ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   MOBILE CAPTURE UI FLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────┐                                   │
│  │     SCREEN 1: CONFIRMATION      │                                   │
│  │                                  │                                   │
│  │  ┌───────────────────────────┐  │                                   │
│  │  │  📝 Assignment Details     │  │                                   │
│  │  │  Subject: Mathematics      │  │                                   │
│  │  │  Assignment: Chapter 5     │  │                                   │
│  │  │  Due: 2025-01-20           │  │                                   │
│  │  └───────────────────────────┘  │                                   │
│  │                                  │                                   │
│  │  ┌───────────────────────────┐  │                                   │
│  │  │  📱 Device Check           │  │                                   │
│  │  │  ✅ Camera: Available      │  │                                   │
│  │  │  ✅ Connection: Stable     │  │                                   │
│  │  └───────────────────────────┘  │                                   │
│  │                                  │                                   │
│  │  [ 📷 Start Camera Capture ]    │                                   │
│  │                                  │                                   │
│  └───────────────┬─────────────────┘                                   │
│                  ▼                                                       │
│  ┌─────────────────────────────────┐                                   │
│  │     SCREEN 2: CAMERA VIEW       │                                   │
│  │                                  │                                   │
│  │  ┌───────────────────────────┐  │                                   │
│  │  │                           │  │                                   │
│  │  │     LIVE CAMERA FEED      │  │                                   │
│  │  │                           │  │                                   │
│  │  │   ┌─── ─── ─── ─── ┐     │  │  ← Edge detection overlay        │
│  │  │   │                 │     │  │    (guides document alignment)    │
│  │  │   │   DOCUMENT      │     │  │                                   │
│  │  │   │   AREA          │     │  │                                   │
│  │  │   │                 │     │  │                                   │
│  │  │   └─── ─── ─── ─── ┘     │  │                                   │
│  │  │                           │  │                                   │
│  │  └───────────────────────────┘  │                                   │
│  │                                  │                                   │
│  │  Pages captured: 3               │                                   │
│  │  [📸 Capture] [🔴 Finish]       │                                   │
│  │                                  │                                   │
│  └───────────────┬─────────────────┘                                   │
│                  ▼                                                       │
│  ┌─────────────────────────────────┐                                   │
│  │     SCREEN 3: REVIEW            │                                   │
│  │                                  │                                   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐       │                                   │
│  │  │ P.1 │ │ P.2 │ │ P.3 │       │ ← Thumbnail grid                  │
│  │  │     │ │     │ │     │       │    Tap to enlarge/retake           │
│  │  │ 🔄  │ │ 🔄  │ │ 🔄  │       │    Drag to reorder                │
│  │  └─────┘ └─────┘ └─────┘       │                                   │
│  │                                  │                                   │
│  │  [+ Add Page] [✅ Confirm]      │                                   │
│  │                                  │                                   │
│  └───────────────┬─────────────────┘                                   │
│                  ▼                                                       │
│  ┌─────────────────────────────────┐                                   │
│  │     SCREEN 4: PROCESSING        │                                   │
│  │                                  │                                   │
│  │       ⏳ Processing...           │                                   │
│  │       ████████░░░ 78%            │                                   │
│  │       Enhancing page 3 of 3     │                                   │
│  │                                  │                                   │
│  └───────────────┬─────────────────┘                                   │
│                  ▼                                                       │
│  ┌─────────────────────────────────┐                                   │
│  │     SCREEN 5: COMPLETE          │                                   │
│  │                                  │                                   │
│  │       ✅ Submission Ready!       │                                   │
│  │       3 pages processed          │                                   │
│  │       PDF size: 1.2 MB           │                                   │
│  │                                  │                                   │
│  │  [📥 Download PDF]              │                                   │
│  │  [You can close this tab]       │                                   │
│  │                                  │                                   │
│  └─────────────────────────────────┘                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 14. DEPLOYMENT ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE SERVICES                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │    nginx     │  │   fastapi   │  │   worker    │  │   worker-2   │ │
│  │             │  │   (uvicorn) │  │  (celery)   │  │  (celery)    │ │
│  │  Port: 443  │─▶│  Port: 8000 │  │             │  │              │ │
│  │  Port: 80   │  │             │  │  CV Pipeline│  │  CV Pipeline │ │
│  └─────────────┘  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │
│                          │                │                 │          │
│                          ▼                ▼                 ▼          │
│                   ┌─────────────┐  ┌─────────────┐                    │
│                   │    redis    │  │  postgresql  │                    │
│                   │  Port: 6379│  │  Port: 5432  │                    │
│                   └─────────────┘  └─────────────┘                    │
│                                                                         │
│                   ┌─────────────┐                                      │
│                   │    minio    │  (Optional, for S3-compatible        │
│                   │  Port: 9000│   object storage)                     │
│                   └─────────────┘                                      │
│                                                                         │
│  VOLUMES:                                                               │
│  ─────────                                                              │
│  • ./storage:/app/storage    (captured images & PDFs)                   │
│  • postgres_data:/var/lib/postgresql/data                              │
│  • redis_data:/data                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 15. ERROR HANDLING & EDGE CASES

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ERROR HANDLING MATRIX                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SCENARIO                        │ HANDLING STRATEGY                    │
│  ────────────────────────────────┼─────────────────────────────────     │
│                                  │                                      │
│  WebSocket disconnects mid-      │ • Images already received are        │
│  capture (network drop)          │   persisted to disk                  │
│                                  │ • Session marked "interrupted"       │
│                                  │ • Reconnection allowed within 5min   │
│                                  │ • Resume from last confirmed page    │
│                                  │                                      │
│  Blurry image captured           │ • Blur detection (Laplacian var)     │
│                                  │ • If score < threshold: warn user    │
│                                  │ • Allow recapture, don't auto-reject │
│                                  │                                      │
│  No document detected in image   │ • Fallback: use full image with     │
│                                  │   margin crop                        │
│                                  │ • Notify user to align paper better  │
│                                  │                                      │
│  Very dark / very bright image   │ • Aggressive histogram equalization  │
│                                  │ • Gamma correction                   │
│                                  │ • If unrecoverable: flag for user    │
│                                  │                                      │
│  Session token expired           │ • Return 401, prompt re-scan        │
│                                  │ • Desktop shows new QR code          │
│                                  │                                      │
│  Multiple devices try to connect │ • Only first connection accepted     │
│  to same session                 │ • Subsequent connections rejected    │
│                                  │   with "session already paired"      │
│                                  │                                      │
│  CV pipeline crashes             │ • Celery retry (max 3 attempts)     │
│                                  │ • On final failure: return raw       │
│                                  │   images as basic PDF                │
│                                  │ • Notify user of degraded quality    │
│                                  │                                      │
│  Browser doesn't support camera  │ • Feature detection on page load    │
│                                  │ • Show "unsupported browser" message │
│                                  │ • Suggest Chrome/Safari              │
│                                  │                                      │
│  User uploads 50+ pages          │ • Hard limit at 50 pages            │
│                                  │ • Show warning at 40 pages           │
│                                  │                                      │
│  Concurrent sessions per user    │ • Limit to 3 active sessions        │
│                                  │ • Auto-expire oldest                 │
│                                  │                                      │
│  Large file sizes                │ • Client-side JPEG quality: 85%     │
│                                  │ • Max resolution: 3000px            │
│                                  │ • Server-side resize if needed       │
│                                  │                                      │
│  Page contains only diagrams     │ • Region classifier detects this    │
│                                  │ • Skip text binarization             │
│                                  │ • Apply diagram-specific pipeline    │
│                                  │                                      │
│  Mixed text + diagram page       │ • Content-aware region segmentation │
│                                  │ • Different processing per region    │
│                                  │ • Smooth compositing at boundaries   │
│                                  │                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 16. PIPELINE PROCESSING STRATEGY: EAGER VS BATCH

```
┌─────────────────────────────────────────────────────────────────────────┐
│              EAGER (RECOMMENDED) vs BATCH PROCESSING                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  EAGER PROCESSING (Recommended for low latency):                       │
│  ──────────────────────────────────────────────                        │
│                                                                         │
│  Page 1 captured ──▶ [Start processing page 1]                         │
│  Page 2 captured ──▶ [Start processing page 2] │ Page 1 still running │
│  Page 3 captured ──▶ [Start processing page 3] │ Page 2 still running │
│  User clicks Finish ──▶ [Wait for remaining] ──▶ [Generate PDF]       │
│                                                                         │
│  Benefits:                                                              │
│  • Processing overlaps with capture time                                │
│  • User waits less after clicking Finish                                │
│  • Better perceived performance                                         │
│                                                                         │
│  Implementation:                                                        │
│  • Each image triggers a Celery task immediately                       │
│  • Tasks run in parallel (multiple workers)                             │
│  • On "Finish": check if all tasks complete, generate PDF              │
│  • Use Celery chord: group of page tasks → PDF generation callback     │
│                                                                         │
│                                                                         │
│  BATCH PROCESSING:                                                      │
│  ─────────────────                                                      │
│                                                                         │
│  Page 1 captured ──▶ [Save to disk]                                    │
│  Page 2 captured ──▶ [Save to disk]                                    │
│  Page 3 captured ──▶ [Save to disk]                                    │
│  User clicks Finish ──▶ [Process all pages] ──▶ [Generate PDF]        │
│                                                                         │
│  When to use:                                                           │
│  • If server resources are limited                                      │
│  • If processing order matters (rare)                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Recommendation: Use Eager Processing** with Celery chord pattern for minimum perceived latency.

---

## 17. INTEGRATION GUIDE (FOR PARENT APPLICATION)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    INTEGRATION ENDPOINTS                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  The parent school application needs to integrate only these APIs:     │
│                                                                         │
│  1. CREATE SESSION                                                      │
│     POST /api/v1/sessions                                              │
│     Headers: X-API-Key: {integration_key}                              │
│     Body: { "assignment_id": "...", "user_id": "..." }                 │
│     Response: { "session_id", "qr_code_base64", "qr_code_url",        │
│                 "ws_url_desktop" }                                      │
│                                                                         │
│  2. EMBED QR CODE                                                       │
│     Use qr_code_base64 to display QR in the assignment UI             │
│                                                                         │
│  3. CONNECT DESKTOP WEBSOCKET                                          │
│     Connect to ws_url_desktop to receive real-time updates             │
│                                                                         │
│  4. GET RESULT                                                          │
│     GET /api/v1/submissions/{session_id}/pdf                           │
│     → Download completed PDF                                           │
│                                                                         │
│  5. UPLOAD TO YOUR SYSTEM                                              │
│     POST /api/v1/submissions/{session_id}/upload                       │
│     → Or simply download PDF and upload to your own storage            │
│                                                                         │
│  WEBHOOK (Optional):                                                    │
│     Configure a webhook URL when creating session                      │
│     Server POSTs to your URL when processing is complete               │
│     Body: { session_id, status, pdf_url, page_count }                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 18. PERFORMANCE BENCHMARKS (ESTIMATED)

| Metric | Target | Notes |
|--------|--------|-------|
| QR scan to WebSocket connection | < 1 second | JWT validation + WS handshake |
| Image transfer (mobile → server) | 200-500ms | 1MB JPEG over 4G/WiFi |
| Single page CV processing | 800-1500ms | On 4-core server with OpenCV |
| Shadow removal | 150-300ms | Morphological operations |
| Document detection + perspective | 100-200ms | Contour-based |
| Text/diagram classification | 200-400ms | Heuristic-based; 500ms+ if CNN |
| Enhancement (text regions) | 200-400ms | Adaptive thresholding |
| Enhancement (diagram regions) | 100-200ms | Lighter processing |
| PDF generation (10 pages) | 300-600ms | img2pdf is very fast |
| Total for 10 pages (eager) | 10-18 seconds | After clicking Finish |
| PDF delivery to client | 500-1500ms | Depends on file size & network |
| Maximum concurrent sessions | 50-100 | Per server instance |

---

## 19. TESTING STRATEGY

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       TESTING STRATEGY                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  UNIT TESTS (pytest)                                                    │
│  ───────────────────                                                    │
│  • CV pipeline stages individually with sample images                  │
│  • JWT token creation/validation                                        │
│  • Session lifecycle logic                                              │
│  • WebSocket message serialization                                     │
│  • QR code generation                                                   │
│  • PDF generation from sample images                                   │
│                                                                         │
│  INTEGRATION TESTS                                                      │
│  ─────────────────                                                      │
│  • Full WebSocket flow (connect, send images, receive PDF)             │
│  • API endpoint chain (create session → capture → download)            │
│  • Database operations                                                  │
│  • Celery task execution                                                │
│                                                                         │
│  CV PIPELINE TESTS                                                      │
│  ─────────────────                                                      │
│  • Test with diverse sample images:                                     │
│    → Well-lit, even background                                         │
│    → Heavy shadows                                                      │
│    → Skewed documents                                                   │
│    → Pages with diagrams                                                │
│    → Mixed text + diagrams                                              │
│    → Low contrast handwriting                                           │
│    → Colored paper                                                      │
│    → Multiple documents in frame                                        │
│  • Visual regression tests (compare output to golden samples)          │
│                                                                         │
│  LOAD TESTS (locust)                                                    │
│  ─────────────────                                                      │
│  • 50 concurrent WebSocket sessions                                     │
│  • Sustained image upload rate                                          │
│  • CV pipeline throughput under load                                    │
│                                                                         │
│  SECURITY TESTS                                                         │
│  ──────────────                                                         │
│  • Expired token rejection                                              │
│  • Invalid session ID handling                                          │
│  • Oversized file rejection                                             │
│  • Rate limiting verification                                           │
│  • CORS enforcement                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 20. DEVELOPMENT PHASES & TIMELINE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PHASES                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  PHASE 1: Foundation (Week 1-2)                                        │
│  ─────────────────────────────                                         │
│  ☐ FastAPI project setup with Docker                                   │
│  ☐ Database models & migrations (Alembic)                              │
│  ☐ Redis setup                                                          │
│  ☐ Session creation API                                                 │
│  ☐ QR code generation                                                   │
│  ☐ JWT authentication                                                   │
│  ☐ Basic health check endpoint                                         │
│                                                                         │
│  PHASE 2: Real-time Communication (Week 2-3)                           │
│  ────────────────────────────────────────────                           │
│  ☐ WebSocket manager (connection tracking, pairing)                    │
│  ☐ Desktop WebSocket handler                                           │
│  ☐ Mobile WebSocket handler                                            │
│  ☐ Binary frame protocol implementation                                │
│  ☐ Session pairing logic (desktop ↔ mobile)                           │
│  ☐ Heartbeat & reconnection logic                                      │
│  ☐ Image reception & disk persistence                                  │
│                                                                         │
│  PHASE 3: Mobile Capture UI (Week 3-4)                                 │
│  ─────────────────────────────────────                                 │
│  ☐ Capture page HTML/JS                                                │
│  ☐ Camera access (getUserMedia)                                        │
│  ☐ Live preview with edge detection overlay                            │
│  ☐ Capture button & image compression                                  │
│  ☐ Page review/reorder/retake UI                                       │
│  ☐ Finish & confirmation flow                                          │
│  ☐ Same-device mode                                                     │
│                                                                         │
│  PHASE 4: CV Pipeline (Week 4-6)                                       │
│  ────────────────────────────────                                       │
│  ☐ Document detection & perspective correction                         │
│  ☐ Shadow removal algorithm                                            │
│  ☐ Contrast & brightness enhancement                                   │
│  ☐ Deskewing & orientation correction                                  │
│  ☐ Text vs diagram region classification                               │
│  ☐ Differential enhancement (text + diagram)                           │
│  ☐ Region compositing                                                   │
│  ☐ DPI normalization                                                    │
│  ☐ Celery task integration                                              │
│  ☐ Eager processing pipeline                                           │
│                                                                         │
│  PHASE 5: PDF & Delivery (Week 6-7)                                   │
│  ────────────────────────────────                                       │
│  ☐ PDF generation from processed images                                │
│  ☐ PDF metadata injection                                              │
│  ☐ PDF optimization/compression                                        │
│  ☐ PDF delivery via WebSocket                                          │
│  ☐ Download endpoint                                                    │
│  ☐ Upload to storage endpoint                                          │
│  ☐ Share endpoint (email/link)                                         │
│                                                                         │
│  PHASE 6: Security & Hardening (Week 7-8)                              │
│  ─────────────────────────────────────────                              │
│  ☐ Rate limiting implementation                                        │
│  ☐ Input validation hardening                                          │
│  ☐ CORS configuration                                                   │
│  ☐ API key authentication for integration                              │
│  ☐ Session cleanup cron job                                            │
│  ☐ Error handling & graceful degradation                               │
│  ☐ Logging & monitoring setup                                          │
│                                                                         │
│  PHASE 7: Testing & Documentation (Week 8-9)                          │
│  ─────────────────────────────────────────────                         │
│  ☐ Unit tests (all modules)                                            │
│  ☐ Integration tests                                                    │
│  ☐ CV pipeline tests with sample images                                │
│  ☐ Load testing                                                         │
│  ☐ API documentation (auto-generated Swagger)                          │
│  ☐ Integration guide for parent app                                    │
│  ☐ Deployment documentation                                            │
│                                                                         │
│  PHASE 8: Optimization & Polish (Week 9-10)                            │
│  ────────────────────────────────────────────                           │
│  ☐ Latency profiling & optimization                                    │
│  ☐ CV pipeline tuning with real-world samples                          │
│  ☐ Mobile UI polish & cross-browser testing                            │
│  ☐ Edge case handling                                                   │
│  ☐ Production deployment configuration                                 │
│  ☐ Final review & handoff                                              │
│                                                                         │
│  TOTAL ESTIMATED TIMELINE: 8-10 weeks (1 developer)                   │
│  TOTAL ESTIMATED TIMELINE: 5-6 weeks (2 developers)                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 21. MONITORING & OBSERVABILITY

| Component | Tool | Metrics |
|-----------|------|---------|
| Application Logs | Python `logging` + structlog → JSON format | Request latency, errors, WS events |
| Metrics | Prometheus + FastAPI instrumentation | Request count, latency percentiles, active WS connections |
| Celery Monitoring | Flower (Celery monitoring tool) | Task queue depth, success/failure rate, processing time |
| Health Checks | `/api/v1/health` endpoint | DB connectivity, Redis connectivity, storage availability |
| Alerting | Prometheus Alertmanager / simple email alerts | Pipeline failures, high error rates, storage full |

---

## 22. CONFIGURATION MANAGEMENT

All configuration via environment variables (12-factor app):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret for JWT signing | Required |
| `API_KEY` | Integration API key | Required |
| `SESSION_EXPIRY_MINUTES` | Session timeout | `30` |
| `MAX_PAGES_PER_SESSION` | Page limit | `50` |
| `MAX_IMAGE_SIZE_MB` | Upload size limit | `10` |
| `STORAGE_PATH` | File storage directory | `./storage` |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | `*` (dev only) |
| `CV_WORKERS` | Number of Celery workers | `2` |
| `JPEG_QUALITY` | Output JPEG quality in PDF | `92` |
| `ENABLE_OCR` | Enable Tesseract OCR layer | `false` |
| `WEBHOOK_URL` | Parent app webhook URL | Optional |
| `LOG_LEVEL` | Logging level | `INFO` |

---

## 23. GLOSSARY

| Term | Definition |
|------|-----------|
| **Session** | A single assignment submission attempt, from QR scan to PDF delivery |
| **Pairing** | The process of connecting a mobile device to a desktop session via QR code |
| **CV Pipeline** | Computer Vision processing chain that enhances captured images |
| **Eager Processing** | Processing each page as it arrives, rather than waiting for all pages |
| **Sauvola Thresholding** | An adaptive binarization method suitable for documents with uneven illumination |
| **CLAHE** | Contrast Limited Adaptive Histogram Equalization — local contrast enhancement |
| **Deskewing** | Correcting the rotational skew of a scanned document |
| **Perspective Correction** | Transforming a photo taken at an angle to a flat, top-down view |
| **Region Classification** | Identifying areas of a page as text, diagram, or blank |
| **Chord (Celery)** | A workflow pattern: run a group of tasks in parallel, then run a callback |

---

## 24. RISKS & MITIGATIONS

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Poor handwriting → bad enhancement | Medium | Medium | Tunable pipeline parameters; avoid over-binarization; keep grayscale fallback |
| Mobile browser camera API inconsistencies | Medium | High | Test on Chrome (Android), Safari (iOS); use adapter layer; provide fallback instructions |
| WebSocket drops on unstable mobile networks | High | Medium | Reconnection logic; persist images server-side immediately; resume support |
| CV pipeline too slow for many pages | Low | Medium | Eager processing; scale Celery workers horizontally; optimize algorithms |
| Security: QR code intercepted | Low | High | Short-lived tokens (15 min); one-time use; HTTPS only |
| Large PDF files | Medium | Low | JPEG compression in PDF; configurable quality; page dimension limits |
| Diagrams lost during text binarization | Medium | High | Content-aware region classification; differential processing; never binarize diagram regions |

---

## 25. CONCLUSION

This document provides a complete architectural blueprint for the **Assignment Submission System** — from the moment a student clicks "Submit" to the final enhanced PDF being stored and available for integration.

**Key Design Principles:**

1. **Low Latency**: WebSocket binary frames, eager processing, async everywhere.
2. **Security-First**: JWT tokens, HTTPS, input validation, rate limiting, session expiry.
3. **Content-Aware Processing**: Diagrams and text are treated differently for optimal output.
4. **Resilience**: Reconnection support, graceful degradation, retry mechanisms.
5. **Integration-Ready**: Clean REST APIs, webhook support, standalone deployment.
6. **Scalable**: Celery workers scale horizontally, stateless API servers, Redis for coordination.

---

*Document Version: 1.0*
*Date: June 2025*
*Confidentiality: Internal — Development Team*

---

I've created an exhaustive technical document covering every aspect of the system. Here's a summary of what's included:

**Key Research Decisions Made:**

1. **WebSocket with Binary Frames** over REST polling — eliminates HTTP overhead per image, achieves ~200ms transfer latency
2. **Eager Processing (Celery Chord pattern)** — process pages as they arrive, so by the time user clicks "Finish," most pages are already processed
3. **Morphological Closing + Division** for shadow removal — fast (~200ms) and effective for the document scanning use case
4. **Content-Aware Region Classification** — critical for preserving diagrams; uses connected component analysis + stroke width features to differentiate text from drawings
5. **Sauvola Thresholding** over Otsu — handles uneven illumination from phone cameras far better
6. **img2pdf for PDF generation** — lossless image embedding, 10x faster than reportlab for image-only PDFs
7. **Redis pub/sub** for pairing desktop ↔ mobile WebSocket connections across potentially different server processes
