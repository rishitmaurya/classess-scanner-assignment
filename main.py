"""
FastAPI Backend — Routes Only.
Uses modern lifespan pattern (no deprecation warnings).
"""

import os
import uuid
import time
import qrcode
import base64
import socket
from io import BytesIO
from datetime import datetime
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    UploadFile, File, Form, Request, HTTPException
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from tunnel_manager import tunnel_manager

from cv_processor import (
    enhance_document_image, 
    create_pdf_from_images, 
    make_preview_b64,
    detect_document_corners,
    process_document_with_corners
)


# ─── Storage ───
sessions: Dict[str, dict] = {}
ws_connections: Dict[str, Dict[str, WebSocket]] = {}


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_base_url(request: Request) -> str:
    if tunnel_manager.public_url:
        return tunnel_manager.public_url
    fh = request.headers.get("x-forwarded-host")
    fp = request.headers.get("x-forwarded-proto")
    if fh:
        return f"{fp or 'https'}://{fh}"
    return f"{request.url.scheme}://{request.headers.get('host', 'localhost:8000')}"


def make_qr_b64(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=config.QR_BOX_SIZE, border=config.QR_BORDER)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=config.QR_FILL_COLOR, back_color=config.QR_BACK_COLOR)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _notify(sid: str, device: str, data: dict):
    if sid in ws_connections and device in ws_connections[sid]:
        try:
            await ws_connections[sid][device].send_json(data)
        except Exception:
            pass


# ─── Lifespan (replaces deprecated on_event) ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    url = await tunnel_manager.start()
    ip = get_local_ip()

    print(f"\n{'='*55}")
    print(f"  📄 Document Scanner")
    print(f"{'='*55}")
    print(f"  Local:  http://localhost:{config.SERVER_PORT}")
    print(f"  LAN:    http://{ip}:{config.SERVER_PORT}")
    if url:
        print(f"  Public: {url}")
    else:
        print(f"  Public: (not available — see options above)")
    print(f"{'='*55}\n")

    yield  # App runs here

    # ── Shutdown ──
    tunnel_manager.stop()


# ─── App Setup ───
app = FastAPI(title="Document Scanner", debug=config.DEBUG, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=config.CORS_METHODS,
    allow_headers=config.CORS_HEADERS,
)

for d in [config.SCANS_DIR, config.PDFS_DIR, config.STATIC_DIR,
          config.TEMPLATES_DIR, "static/css", "static/js"]:
    os.makedirs(d, exist_ok=True)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)


# ═══ PAGES ═══

@app.get(config.ROUTE_HOME, response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, "base_url": get_base_url(request)
    })


@app.get(config.ROUTE_SCAN, response_class=HTMLResponse)
async def scanner_page(request: Request, session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session expired")
    return templates.TemplateResponse("scanner.html", {
        "request": request, "session_id": session_id,
        "base_url": get_base_url(request)
    })


# ═══ API ═══

@app.post(config.ROUTE_CREATE_SESSION)
async def create_session(request: Request):
    sid = str(uuid.uuid4())[:config.SESSION_ID_LENGTH]
    sessions[sid] = {
        "id": sid, "created_at": datetime.now().isoformat(),
        "pages": {}, "status": "active", "pdf_path": None,
        "page_previews": {}
    }
    base = get_base_url(request)
    scan_url = f"{base}/scan/{sid}"
    print(f"[+] Session {sid} → {scan_url}")
    return JSONResponse({
        "session_id": sid,
        "qr_code": f"data:image/png;base64,{make_qr_b64(scan_url)}",
        "scan_url": scan_url, "base_url": base
    })


@app.post(config.ROUTE_UPLOAD_PAGE)
async def upload_page(session_id: str, file: UploadFile = File(...),
                      page_number: int = Form(...)):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    raw = await file.read()

    print(f"  [upload] session={session_id} page={page_number} size={len(raw)} bytes")

    enhanced = enhance_document_image(raw)
    preview = make_preview_b64(enhanced)

    fname = f"{session_id}_p{page_number}_{int(time.time())}.jpg"
    fpath = os.path.join(config.SCANS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(enhanced)

    sessions[session_id]["pages"][page_number] = {
        "page_number": page_number,
        "filepath": fpath,
        "filename": fname
    }
    sessions[session_id]["page_previews"][page_number] = f"data:image/jpeg;base64,{preview}"

    total = len(sessions[session_id]["pages"])

    await _notify(session_id, "desktop", {
        "type": "page_uploaded",
        "page_number": page_number,
        "total_pages": total,
        "preview": f"data:image/jpeg;base64,{preview}"
    })

    print(f"  [done] page={page_number} total={total} enhanced_size={len(enhanced)} bytes")

    return JSONResponse({
        "status": "success",
        "page_number": page_number,
        "total_pages": total,
        "preview": f"data:image/jpeg;base64,{preview}"
    })


@app.delete(config.ROUTE_DELETE_PAGE)
async def delete_page(session_id: str, page_number: int):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    sessions[session_id]["pages"].pop(page_number, None)
    sessions[session_id]["page_previews"].pop(page_number, None)
    total = len(sessions[session_id]["pages"])

    await _notify(session_id, "desktop", {
        "type": "page_deleted", "page_number": page_number, "total_pages": total
    })
    return JSONResponse({"status": "deleted", "total_pages": total})


@app.post(config.ROUTE_FINISH)
async def finish_scanning(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    session = sessions[session_id]
    pages_dict = session["pages"]

    if not pages_dict:
        raise HTTPException(400, "No pages scanned")

    sorted_nums = sorted(pages_dict.keys())
    paths = [pages_dict[n]["filepath"] for n in sorted_nums]
    valid_paths = [p for p in paths if os.path.exists(p)]

    if not valid_paths:
        raise HTTPException(400, "No valid page files found")

    pdf_name = f"assignment_{session_id}_{int(time.time())}.pdf"
    pdf_path = os.path.join(config.PDFS_DIR, pdf_name)
    create_pdf_from_images(valid_paths, pdf_path)

    session["pdf_path"] = pdf_path
    session["status"] = "completed"

    dl_url = f"/api/download-pdf/{session_id}"
    pv_url = f"/api/preview-pdf/{session_id}"
    total = len(valid_paths)

    previews = []
    for n in sorted_nums:
        if n in session["page_previews"]:
            previews.append({"page": n, "src": session["page_previews"][n]})

    msg = {
        "type": "pdf_ready", "pdf_url": dl_url, "preview_url": pv_url,
        "total_pages": total, "filename": pdf_name, "previews": previews
    }

    await _notify(session_id, "desktop", msg)
    await _notify(session_id, "mobile", msg)

    print(f"  [finish] session={session_id} pages={total} pdf={pdf_name}")

    return JSONResponse({
        "status": "success", "pdf_url": dl_url, "preview_url": pv_url,
        "filename": pdf_name, "total_pages": total, "previews": previews
    })


@app.get(config.ROUTE_DOWNLOAD)
async def download_pdf(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    p = sessions[session_id].get("pdf_path")
    if not p or not os.path.exists(p):
        raise HTTPException(404, "PDF not ready")
    return FileResponse(p, media_type="application/pdf",
                        filename=os.path.basename(p))


@app.get(config.ROUTE_PREVIEW)
async def preview_pdf(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    p = sessions[session_id].get("pdf_path")
    if not p or not os.path.exists(p):
        raise HTTPException(404, "PDF not ready")
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


@app.get(config.ROUTE_SESSION_STATUS)
async def session_status(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    s = sessions[session_id]
    previews = []
    for n in sorted(s["pages"].keys()):
        if n in s["page_previews"]:
            previews.append({"page": n, "src": s["page_previews"][n]})
    return JSONResponse({
        "session_id": session_id, "status": s["status"],
        "total_pages": len(s["pages"]), "pages": previews,
        "pdf_ready": s["pdf_path"] is not None,
        "pdf_url": f"/api/download-pdf/{session_id}" if s["pdf_path"] else None
    })


@app.post(config.ROUTE_SUBMIT)
async def submit_assignment(session_id: str, student_name: str = Form(...),
                             assignment_title: str = Form(...)):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    if not sessions[session_id].get("pdf_path"):
        raise HTTPException(400, "PDF not generated")
    return JSONResponse({"status": "success", "message": "Assignment submitted!"})


@app.post(config.ROUTE_SET_URL)
async def set_public_url(request: Request):
    body = await request.json()
    tunnel_manager.public_url = body.get("url", "").rstrip("/")
    return {"status": "ok", "public_url": tunnel_manager.public_url}


@app.get(config.ROUTE_GET_URL)
async def get_public_url(request: Request):
    return {
        "base_url": get_base_url(request),
        "tunnel_active": tunnel_manager.public_url is not None,
        "local_ip": get_local_ip()
    }


@app.post(config.ROUTE_DETECT_TUNNEL)
async def detect_tunnel():
    url = await tunnel_manager._detect_existing_ngrok()
    if url:
        tunnel_manager.public_url = url
        return {"status": "found", "url": url}
    return {"status": "not_found"}


@app.post("/api/detect-corners/{session_id}")
async def detect_corners(session_id: str, file: UploadFile = File(...)):
    """Detect document corners in uploaded image frame."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    
    raw = await file.read()
    corners = detect_document_corners(raw)
    
    return JSONResponse({
        "status": "success",
        "corners": corners  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] as percentages
    })


@app.post("/api/upload-page-with-corners/{session_id}")
async def upload_page_with_corners(
    session_id: str,
    file: UploadFile = File(...),
    page_number: int = Form(...),
    corners: str = Form(...)  # JSON string: "[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"
):
    """Upload page with user-specified corner points."""
    import json
    
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    
    raw = await file.read()
    
    try:
        corner_points = json.loads(corners)
    except:
        corner_points = None
    
    print(f"  [upload] session={session_id} page={page_number} corners={corner_points is not None}")
    
    if corner_points and len(corner_points) == 4:
        # Process with user corners
        enhanced = process_document_with_corners(raw, corner_points)
    else:
        # Fallback to auto-detect
        enhanced = enhance_document_image(raw)
    
    preview = make_preview_b64(enhanced)
    
    fname = f"{session_id}_p{page_number}_{int(time.time())}.jpg"
    fpath = os.path.join(config.SCANS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(enhanced)
    
    sessions[session_id]["pages"][page_number] = {
        "page_number": page_number,
        "filepath": fpath,
        "filename": fname
    }
    sessions[session_id]["page_previews"][page_number] = f"data:image/jpeg;base64,{preview}"
    
    total = len(sessions[session_id]["pages"])
    
    await _notify(session_id, "desktop", {
        "type": "page_uploaded",
        "page_number": page_number,
        "total_pages": total,
        "preview": f"data:image/jpeg;base64,{preview}"
    })
    
    return JSONResponse({
        "status": "success",
        "page_number": page_number,
        "total_pages": total,
        "preview": f"data:image/jpeg;base64,{preview}"
    })

# ═══ WEBSOCKET ═══

@app.websocket(config.ROUTE_WS)
async def ws_endpoint(websocket: WebSocket, session_id: str, device_type: str):
    await websocket.accept()
    if session_id not in ws_connections:
        ws_connections[session_id] = {}
    ws_connections[session_id][device_type] = websocket
    other = "desktop" if device_type == "mobile" else "mobile"
    print(f"[WS] {device_type} → {session_id}")
    await _notify(session_id, other, {"type": "device_connected", "device": device_type})

    try:
        while True:
            data = await websocket.receive_json()
            await _notify(session_id, other, data)
    except WebSocketDisconnect:
        print(f"[WS] {device_type} ✗ {session_id}")
        if session_id in ws_connections:
            ws_connections[session_id].pop(device_type, None)
            await _notify(session_id, other,
                          {"type": "device_disconnected", "device": device_type})
            if not ws_connections[session_id]:
                del ws_connections[session_id]


# ═══ RUN ═══

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)