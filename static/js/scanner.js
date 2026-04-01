/* ═══════════════════════════════════════
   MOBILE SCANNER — Fixed
   ═══════════════════════════════════════ */

let ws = null;
let stream = null;
let pg = 1;
let confirmed = {};
let pendingBlob = null;
let facing = 'environment';
let flash = false;
let isUploading = false;

document.addEventListener('DOMContentLoaded', () => {
    initWS();
    initCam();
});

function initWS() {
    const wsBase = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    const url = `${wsBase}/ws/${SESSION_ID}/mobile`;

    ws = new WebSocket(url);
    ws.onopen = () => {
        const d = document.getElementById('connDot');
        d.className = 'conn-dot connected';
        d.querySelector('span').textContent = 'Connected';
    };
    ws.onmessage = e => {
        const data = JSON.parse(e.data);
        if (data.type === 'pdf_ready') showDone(data);
    };
    ws.onclose = () => {
        const d = document.getElementById('connDot');
        d.className = 'conn-dot connecting';
        d.querySelector('span').textContent = 'Reconnecting...';
        setTimeout(initWS, 3000);
    };
    ws.onerror = () => {};
}

async function initCam() {
    try {
        if (stream) stream.getTracks().forEach(t => t.stop());
        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: facing, width: { ideal: 1920 }, height: { ideal: 1080 } }
        });
        document.getElementById('vid').srcObject = stream;
    } catch (e) {
        alert('Camera access denied.\n\nEnsure:\n• Using HTTPS URL\n• Camera permission allowed');
    }
}

function capture() {
    if (isUploading) return;

    const v = document.getElementById('vid');
    const c = document.getElementById('cvs');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0);

    const ov = document.querySelector('.cam-ov');
    ov.style.background = 'rgba(255,255,255,.6)';
    setTimeout(() => ov.style.background = 'transparent', 100);

    c.toBlob(b => {
        pendingBlob = b;
        document.getElementById('prevImg').src = URL.createObjectURL(b);
        document.getElementById('prevPageNum').textContent = pg;
        document.getElementById('prevOv').style.display = 'flex';
    }, 'image/jpeg', 0.92);
}

function retake() {
    document.getElementById('prevOv').style.display = 'none';
    pendingBlob = null;
}

async function accept() {
    if (!pendingBlob || isUploading) return;
    isUploading = true;

    document.getElementById('prevOv').style.display = 'none';

    const thisPage = pg;
    const fd = new FormData();
    fd.append('file', pendingBlob, `page_${thisPage}.jpg`);
    fd.append('page_number', thisPage);

    try {
        const r = await fetch(`/api/upload-page/${SESSION_ID}`, { method: 'POST', body: fd });
        const d = await r.json();

        if (d.status === 'success') {
            const src = d.preview || URL.createObjectURL(pendingBlob);
            confirmed[thisPage] = { url: src };

            // Remove old thumb if retake, add new
            removeThumb(thisPage);
            addThumb(thisPage, src);

            const count = Object.keys(confirmed).length;
            pg++;

            document.getElementById('pgLabel').textContent = `Page ${pg}`;
            document.getElementById('scannedLabel').textContent = `${count} scanned`;
            document.getElementById('finBtn').style.display = 'flex';
            document.getElementById('inlineThumbs').style.display = 'block';
        }
    } catch (e) {
        alert('Upload failed. Try again.');
    }

    pendingBlob = null;
    isUploading = false;
}

function addThumb(num, src) {
    const list = document.getElementById('thumbList');
    const t = document.createElement('div');
    t.className = 'm-thumb';
    t.id = `mt-${num}`;
    t.innerHTML = `<img src="${src}" alt="P${num}"><div class="tn">${num}</div>`;
    list.appendChild(t);
}

function removeThumb(num) {
    const el = document.getElementById(`mt-${num}`);
    if (el) el.remove();
}

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
    initCam();
}

async function finish() {
    const count = Object.keys(confirmed).length;
    if (count === 0) return alert('Scan at least one page');

    if (stream) stream.getTracks().forEach(t => t.stop());

    document.getElementById('processing').style.display = 'flex';
    const bar = document.getElementById('progBar');
    let p = 0;
    const iv = setInterval(() => {
        p += 3;
        bar.style.width = Math.min(p, 90) + '%';
        const msg = document.getElementById('procMsg');
        if (p > 20) msg.textContent = 'Detecting document...';
        if (p > 40) msg.textContent = 'Correcting orientation...';
        if (p > 60) msg.textContent = 'Enhancing readability...';
        if (p > 80) msg.textContent = 'Generating PDF...';
    }, 200);

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

        setTimeout(() => showDone(d), 600);
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

    const dv = document.getElementById('doneView');
    dv.style.display = 'flex';
    document.getElementById('doneInfo').textContent =
        `${d.total_pages} page${d.total_pages > 1 ? 's' : ''} scanned and enhanced`;

    document.getElementById('dlLink').href = d.pdf_url;

    // Large PDF preview
    if (d.preview_url || d.pdf_url) {
        document.getElementById('mobilePdfFrame').src = d.preview_url || d.pdf_url;
        document.getElementById('mobilePdfPreview').style.display = 'block';
    }

    // Thumbnails
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
            await navigator.share({ title: 'Assignment', files: [new File([b], 'assignment.pdf', { type: 'application/pdf' })] });
            return;
        } catch (_) {}
    }
    const full = url.startsWith('http') ? url : location.origin + url;
    navigator.clipboard?.writeText(full);
    alert('Download link copied!');
}