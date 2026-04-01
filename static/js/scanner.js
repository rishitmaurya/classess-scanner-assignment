/* ═══════════════════════════════════════
   MOBILE SCANNER — Real-time Document Detection
   with Draggable Corner Adjustment
   ═══════════════════════════════════════ */

// ─── State ───
let ws = null;
let stream = null;
let nextPageNum = 1;
let confirmed = {};
let facing = 'environment';
let flash = false;
let isUploading = false;

// Detection state
let detectionInterval = null;
let currentCorners = null;  // Current detected corners [[x,y], ...]
let isDetecting = false;
let lastDetectTime = 0;

// Preview state
let capturedImageData = null;
let capturedBlob = null;
let previewCorners = null;  // Corners being adjusted in preview
let draggingCorner = null;

// ═══════════════════════════════════════
//  INITIALIZATION
// ═══════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initWS();
    initCam();
    initCornerDrag();
});

function initWS() {
    const wsBase = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    ws = new WebSocket(`${wsBase}/ws/${SESSION_ID}/mobile`);
    
    ws.onopen = () => {
        document.getElementById('connDot').className = 'conn-dot connected';
        document.getElementById('connDot').querySelector('span').textContent = 'Connected';
    };
    ws.onmessage = e => {
        const data = JSON.parse(e.data);
        if (data.type === 'pdf_ready') showDone(data);
    };
    ws.onclose = () => {
        document.getElementById('connDot').className = 'conn-dot connecting';
        document.getElementById('connDot').querySelector('span').textContent = 'Reconnecting...';
        setTimeout(initWS, 3000);
    };
}

async function initCam() {
    try {
        if (stream) stream.getTracks().forEach(t => t.stop());
        
        stream = await navigator.mediaDevices.getUserMedia({
            video: { 
                facingMode: facing, 
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            }
        });
        
        const vid = document.getElementById('vid');
        vid.srcObject = stream;
        
        vid.onloadedmetadata = () => {
            startDetection();
        };
    } catch (e) {
        alert('Camera access denied.\n\nEnsure:\n• Using HTTPS URL\n• Camera permission allowed');
    }
}

// ═══════════════════════════════════════
//  REAL-TIME DOCUMENT DETECTION
// ═══════════════════════════════════════

function startDetection() {
    if (detectionInterval) clearInterval(detectionInterval);
    
    // Detect every 200ms for smooth real-time feedback
    detectionInterval = setInterval(() => {
        if (!isDetecting && !isUploading) {
            detectDocumentEdges();
        }
    }, 200);
}

function stopDetection() {
    if (detectionInterval) {
        clearInterval(detectionInterval);
        detectionInterval = null;
    }
}

async function detectDocumentEdges() {
    const vid = document.getElementById('vid');
    if (!vid.videoWidth || !vid.videoHeight) return;
    
    isDetecting = true;
    
    try {
        // Capture low-res frame for detection (faster)
        const detectCanvas = document.getElementById('detectCanvas');
        const maxDim = 320;
        const scale = Math.min(maxDim / vid.videoWidth, maxDim / vid.videoHeight);
        
        detectCanvas.width = vid.videoWidth * scale;
        detectCanvas.height = vid.videoHeight * scale;
        
        const ctx = detectCanvas.getContext('2d');
        ctx.drawImage(vid, 0, 0, detectCanvas.width, detectCanvas.height);
        
        // Get image data for local processing
        const imageData = ctx.getImageData(0, 0, detectCanvas.width, detectCanvas.height);
        
        // Detect edges locally (faster than server round-trip)
        const corners = detectEdgesLocal(imageData, detectCanvas.width, detectCanvas.height);
        
        if (corners) {
            currentCorners = corners;
            updateDetectionOverlay(corners);
            setDetectStatus(true, 'Document detected');
        } else {
            // Show default rectangle
            currentCorners = [[0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95]];
            updateDetectionOverlay(currentCorners);
            setDetectStatus(false, 'Position document in frame');
        }
    } catch (e) {
        console.error('Detection error:', e);
    }
    
    isDetecting = false;
}

function detectEdgesLocal(imageData, width, height) {
    /**
     * Local edge detection using simple but effective algorithm.
     * Finds the largest bright rectangle (paper) in the image.
     */
    const data = imageData.data;
    
    // Convert to grayscale and find bright regions (paper)
    const gray = new Uint8Array(width * height);
    for (let i = 0; i < width * height; i++) {
        const r = data[i * 4];
        const g = data[i * 4 + 1];
        const b = data[i * 4 + 2];
        gray[i] = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
    }
    
    // Simple threshold to find paper (bright areas)
    const threshold = getOtsuThreshold(gray);
    const binary = new Uint8Array(width * height);
    for (let i = 0; i < gray.length; i++) {
        binary[i] = gray[i] > threshold ? 255 : 0;
    }
    
    // Find bounding rectangle of largest white region
    const bounds = findLargestWhiteRegion(binary, width, height);
    
    if (bounds && bounds.area > (width * height * 0.1)) {
        // Convert to percentage coordinates
        return [
            [bounds.x1 / width, bounds.y1 / height],
            [bounds.x2 / width, bounds.y1 / height],
            [bounds.x2 / width, bounds.y2 / height],
            [bounds.x1 / width, bounds.y2 / height]
        ];
    }
    
    return null;
}

function getOtsuThreshold(gray) {
    // Compute histogram
    const hist = new Array(256).fill(0);
    for (let i = 0; i < gray.length; i++) {
        hist[gray[i]]++;
    }
    
    const total = gray.length;
    let sum = 0;
    for (let i = 0; i < 256; i++) sum += i * hist[i];
    
    let sumB = 0, wB = 0, wF = 0;
    let maxVar = 0, threshold = 0;
    
    for (let t = 0; t < 256; t++) {
        wB += hist[t];
        if (wB === 0) continue;
        wF = total - wB;
        if (wF === 0) break;
        
        sumB += t * hist[t];
        const mB = sumB / wB;
        const mF = (sum - sumB) / wF;
        const varBetween = wB * wF * (mB - mF) * (mB - mF);
        
        if (varBetween > maxVar) {
            maxVar = varBetween;
            threshold = t;
        }
    }
    
    return threshold;
}

function findLargestWhiteRegion(binary, width, height) {
    // Simple connected component analysis
    // Find bounding box of largest white region
    
    let minX = width, minY = height, maxX = 0, maxY = 0;
    let whiteCount = 0;
    
    // Apply morphological closing (simple version)
    const closed = new Uint8Array(binary);
    
    // Find bounds of white pixels
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            if (closed[y * width + x] === 255) {
                whiteCount++;
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            }
        }
    }
    
    if (whiteCount < 100) return null;
    
    // Add small margin
    const margin = 5;
    minX = Math.max(0, minX - margin);
    minY = Math.max(0, minY - margin);
    maxX = Math.min(width - 1, maxX + margin);
    maxY = Math.min(height - 1, maxY + margin);
    
    return {
        x1: minX, y1: minY,
        x2: maxX, y2: maxY,
        area: (maxX - minX) * (maxY - minY)
    };
}

function updateDetectionOverlay(corners) {
    const vid = document.getElementById('vid');
    const overlay = document.getElementById('detectionOverlay');
    const poly = document.getElementById('detectionPoly');
    
    const rect = vid.getBoundingClientRect();
    overlay.style.width = rect.width + 'px';
    overlay.style.height = rect.height + 'px';
    
    // Convert percentage to pixels
    const points = corners.map(c => [c[0] * rect.width, c[1] * rect.height]);
    
    // Update polygon
    poly.setAttribute('points', points.map(p => p.join(',')).join(' '));
    
    // Update corner handles
    for (let i = 0; i < 4; i++) {
        const handle = document.getElementById(`corner${i}`);
        handle.setAttribute('cx', points[i][0]);
        handle.setAttribute('cy', points[i][1]);
    }
}

function setDetectStatus(found, text) {
    const status = document.getElementById('detectStatus');
    status.className = 'detect-status' + (found ? ' found' : '');
    status.querySelector('span').textContent = text;
    status.querySelector('i').className = found ? 'fas fa-check-circle' : 'fas fa-search';
}

// ═══════════════════════════════════════
//  CAPTURE
// ═══════════════════════════════════════

async function capture() {
    if (isUploading) return;
    
    stopDetection();
    
    const vid = document.getElementById('vid');
    const cvs = document.getElementById('cvs');
    
    // Capture at FULL resolution
    cvs.width = vid.videoWidth;
    cvs.height = vid.videoHeight;
    
    const ctx = cvs.getContext('2d');
    ctx.drawImage(vid, 0, 0);
    
    // Flash effect
    const overlay = document.getElementById('detectionOverlay');
    overlay.style.background = 'rgba(255,255,255,0.6)';
    setTimeout(() => overlay.style.background = 'transparent', 100);
    
    // Store captured image
    capturedImageData = ctx.getImageData(0, 0, cvs.width, cvs.height);
    
    // Convert to blob for upload
    capturedBlob = await new Promise(resolve => {
        cvs.toBlob(resolve, 'image/jpeg', 0.95);
    });
    
    // Use current detected corners for preview
    previewCorners = currentCorners ? [...currentCorners.map(c => [...c])] : 
        [[0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95]];
    
    showPreview();
}

function showPreview() {
    const cvs = document.getElementById('cvs');
    const previewCanvas = document.getElementById('previewCanvas');
    const previewOverlay = document.getElementById('previewOverlay');
    
    // Fit preview to screen
    const maxW = window.innerWidth - 32;
    const maxH = window.innerHeight * 0.55;
    
    const scale = Math.min(maxW / cvs.width, maxH / cvs.height);
    
    previewCanvas.width = cvs.width * scale;
    previewCanvas.height = cvs.height * scale;
    
    previewCanvas.style.width = previewCanvas.width + 'px';
    previewCanvas.style.height = previewCanvas.height + 'px';
    
    const ctx = previewCanvas.getContext('2d');
    ctx.drawImage(cvs, 0, 0, previewCanvas.width, previewCanvas.height);
    
    // Setup overlay
    previewOverlay.style.width = previewCanvas.width + 'px';
    previewOverlay.style.height = previewCanvas.height + 'px';
    
    updatePreviewCorners();
    
    document.getElementById('prevPageNum').textContent = nextPageNum;
    document.getElementById('prevOv').style.display = 'flex';
}

function updatePreviewCorners() {
    const canvas = document.getElementById('previewCanvas');
    const poly = document.getElementById('previewPoly');
    
    const w = canvas.width;
    const h = canvas.height;
    
    // Convert percentage to pixels
    const points = previewCorners.map(c => [c[0] * w, c[1] * h]);
    
    // Update polygon
    poly.setAttribute('points', points.map(p => p.join(',')).join(' '));
    
    // Update corner handles
    for (let i = 0; i < 4; i++) {
        const handle = document.getElementById(`prevCorner${i}`);
        handle.setAttribute('cx', points[i][0]);
        handle.setAttribute('cy', points[i][1]);
    }
}

// ═══════════════════════════════════════
//  DRAGGABLE CORNERS
// ═══════════════════════════════════════

function initCornerDrag() {
    const overlay = document.getElementById('previewOverlay');
    
    // Touch events
    overlay.addEventListener('touchstart', onCornerTouchStart, { passive: false });
    overlay.addEventListener('touchmove', onCornerTouchMove, { passive: false });
    overlay.addEventListener('touchend', onCornerTouchEnd);
    
    // Mouse events
    overlay.addEventListener('mousedown', onCornerMouseDown);
    document.addEventListener('mousemove', onCornerMouseMove);
    document.addEventListener('mouseup', onCornerMouseUp);
}

function onCornerTouchStart(e) {
    const touch = e.touches[0];
    const target = document.elementFromPoint(touch.clientX, touch.clientY);
    
    if (target && target.classList.contains('prev-corner')) {
        e.preventDefault();
        draggingCorner = parseInt(target.dataset.idx);
    }
}

function onCornerTouchMove(e) {
    if (draggingCorner === null) return;
    e.preventDefault();
    
    const touch = e.touches[0];
    updateCornerPosition(touch.clientX, touch.clientY);
}

function onCornerTouchEnd() {
    draggingCorner = null;
}

function onCornerMouseDown(e) {
    if (e.target.classList.contains('prev-corner')) {
        draggingCorner = parseInt(e.target.dataset.idx);
        e.preventDefault();
    }
}

function onCornerMouseMove(e) {
    if (draggingCorner === null) return;
    updateCornerPosition(e.clientX, e.clientY);
}

function onCornerMouseUp() {
    draggingCorner = null;
}

function updateCornerPosition(clientX, clientY) {
    const canvas = document.getElementById('previewCanvas');
    const rect = canvas.getBoundingClientRect();
    
    // Calculate position relative to canvas
    let x = (clientX - rect.left) / rect.width;
    let y = (clientY - rect.top) / rect.height;
    
    // Clamp to canvas bounds
    x = Math.max(0.01, Math.min(0.99, x));
    y = Math.max(0.01, Math.min(0.99, y));
    
    // Update corner
    previewCorners[draggingCorner] = [x, y];
    
    updatePreviewCorners();
}

// ═══════════════════════════════════════
//  ACCEPT / RETAKE
// ═══════════════════════════════════════

function retake() {
    document.getElementById('prevOv').style.display = 'none';
    capturedBlob = null;
    capturedImageData = null;
    previewCorners = null;
    startDetection();
}

async function accept() {
    if (!capturedBlob || isUploading) return;
    isUploading = true;
    
    document.getElementById('prevOv').style.display = 'none';
    
    const thisPage = nextPageNum;
    
    // Upload with corner data
    const fd = new FormData();
    fd.append('file', capturedBlob, `page_${thisPage}.jpg`);
    fd.append('page_number', thisPage);
    fd.append('corners', JSON.stringify(previewCorners));
    
    try {
        const r = await fetch(`/api/upload-page-with-corners/${SESSION_ID}`, {
            method: 'POST',
            body: fd
        });
        const d = await r.json();
        
        if (d.status === 'success') {
            const src = d.preview;
            confirmed[thisPage] = { url: src };
            
            removeThumb(thisPage);
            addThumb(thisPage, src);
            
            nextPageNum++;
            updateUI();
        } else {
            alert('Upload failed: ' + (d.detail || 'Unknown error'));
        }
    } catch (e) {
        console.error(e);
        alert('Upload failed. Try again.');
    }
    
    capturedBlob = null;
    capturedImageData = null;
    previewCorners = null;
    isUploading = false;
    
    startDetection();
}

// ═══════════════════════════════════════
//  UI HELPERS
// ═══════════════════════════════════════

function updateUI() {
    const count = Object.keys(confirmed).length;
    document.getElementById('pgLabel').textContent = `Page ${nextPageNum}`;
    document.getElementById('scannedLabel').textContent = `${count} scanned`;
    
    if (count > 0) {
        document.getElementById('finBtn').style.display = 'flex';
        document.getElementById('inlineThumbs').style.display = 'block';
    } else {
        document.getElementById('finBtn').style.display = 'none';
        document.getElementById('inlineThumbs').style.display = 'none';
    }
}

function addThumb(num, src) {
    const list = document.getElementById('thumbList');
    const t = document.createElement('div');
    t.className = 'm-thumb';
    t.id = `mt-${num}`;
    t.innerHTML = `
        <img src="${src}" alt="P${num}">
        <div class="tn">${num}</div>
        <button class="thumb-x" onclick="event.stopPropagation();deletePage(${num})">
            <i class="fas fa-times"></i>
        </button>
    `;
    list.appendChild(t);
}

function removeThumb(num) {
    const el = document.getElementById(`mt-${num}`);
    if (el) el.remove();
}

async function deletePage(num) {
    removeThumb(num);
    delete confirmed[num];
    updateUI();
    
    try {
        await fetch(`/api/delete-page/${SESSION_ID}/${num}`, { method: 'DELETE' });
    } catch (e) {
        console.error(e);
    }
    
    if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ 
            type: 'page_deleted', 
            page_number: num, 
            total_pages: Object.keys(confirmed).length 
        }));
    }
}

// ═══════════════════════════════════════
//  CAMERA CONTROLS
// ═══════════════════════════════════════

function toggleFlash() {
    const track = stream?.getVideoTracks()[0];
    if (!track) return;
    try {
        const caps = track.getCapabilities?.();
        if (caps?.torch) {
            flash = !flash;
            track.applyConstraints({ advanced: [{ torch: flash }] });
            document.getElementById('flashIcon').style.color = flash ? 'var(--accent)' : '#fff';
        }
    } catch (_) {}
}

function flipCam() {
    facing = facing === 'environment' ? 'user' : 'environment';
    stopDetection();
    initCam();
}

// ═══════════════════════════════════════
//  FINISH
// ═══════════════════════════════════════

async function finish() {
    const count = Object.keys(confirmed).length;
    if (count === 0) return alert('Scan at least one page');
    
    stopDetection();
    if (stream) stream.getTracks().forEach(t => t.stop());
    
    document.getElementById('processing').style.display = 'flex';
    const bar = document.getElementById('progBar');
    let p = 0;
    
    const iv = setInterval(() => {
        p += 4;
        bar.style.width = Math.min(p, 90) + '%';
        const msg = document.getElementById('procMsg');
        if (p > 25) msg.textContent = 'Applying perspective correction...';
        if (p > 50) msg.textContent = 'Enhancing quality...';
        if (p > 75) msg.textContent = 'Generating PDF...';
    }, 150);
    
    try {
        const r = await fetch(`/api/finish-scanning/${SESSION_ID}`, { method: 'POST' });
        const d = await r.json();
        
        clearInterval(iv);
        bar.style.width = '100%';
        document.getElementById('procMsg').textContent = 'Done!';
        
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'pdf_ready',
                pdf_url: d.pdf_url,
                preview_url: d.preview_url,
                total_pages: d.total_pages,
                filename: d.filename,
                previews: d.previews || []
            }));
        }
        
        setTimeout(() => showDone(d), 500);
    } catch (e) {
        clearInterval(iv);
        document.getElementById('processing').style.display = 'none';
        alert('Error generating PDF. Try again.');
    }
}

function showDone(d) {
    document.getElementById('processing').style.display = 'none';
    document.getElementById('camSection').style.display = 'none';
    document.getElementById('controlSection').style.display = 'none';
    
    document.getElementById('doneView').style.display = 'flex';
    document.getElementById('doneInfo').textContent = 
        `${d.total_pages} page${d.total_pages > 1 ? 's' : ''} — cropped & enhanced`;
    
    document.getElementById('dlLink').href = d.pdf_url;
    
    if (d.preview_url || d.pdf_url) {
        document.getElementById('mobilePdfFrame').src = d.preview_url || d.pdf_url;
        document.getElementById('mobilePdfPreview').style.display = 'block';
    }
    
    const dt = document.getElementById('doneThumbs');
    dt.innerHTML = '';
    
    if (d.previews && d.previews.length > 0) {
        d.previews.forEach(p => {
            const t = document.createElement('div');
            t.className = 'm-thumb';
            t.innerHTML = `<img src="${p.src}" alt="P${p.page}"><div class="tn">${p.page}</div>`;
            dt.appendChild(t);
        });
    } else {
        Object.keys(confirmed).sort((a, b) => a - b).forEach(n => {
            const t = document.createElement('div');
            t.className = 'm-thumb';
            t.innerHTML = `<img src="${confirmed[n].url}" alt="P${n}"><div class="tn">${n}</div>`;
            dt.appendChild(t);
        });
    }
}

async function sharePDF() {
    const url = document.getElementById('dlLink').href;
    if (navigator.share) {
        try {
            const r = await fetch(url);
            const b = await r.blob();
            await navigator.share({ 
                title: 'Assignment', 
                files: [new File([b], 'assignment.pdf', { type: 'application/pdf' })] 
            });
            return;
        } catch (_) {}
    }
    const full = url.startsWith('http') ? url : location.origin + url;
    navigator.clipboard?.writeText(full);
    alert('Download link copied!');
}