/* ═══════════════════════════════════════
   DESKTOP — Scanner Modal
   ═══════════════════════════════════════ */

let session = null;
let assignment = '';
let ws = null;
let stream = null;
let confirmedPages = {};  // { pageNumber: { preview: "data:..." } }
let pgNum = 1;
let localMode = false;
let currentBlob = null;
let isUploading = false;

// ═══ Open / Close ═══

async function openScanner(title) {
    assignment = title;
    document.getElementById('assignmentTitle').textContent = title;
    document.getElementById('modal').style.display = 'flex';

    confirmedPages = {};
    pgNum = 1;
    localMode = false;
    isUploading = false;
    currentBlob = null;

    clearElement('localThumbs');
    clearElement('remoteThumbs');
    clearElement('reviewThumbs');
    hide('finLocalBtn');
    hide('pdfPreviewWrap');
    goStep(1);

    try {
        const r = await fetch('/api/create-session', { method: 'POST' });
        const d = await r.json();
        session = d;

        document.getElementById('qrArea').innerHTML =
            `<img src="${d.qr_code}" alt="QR">
             <p style="font-size:.72em;color:#aaa;margin-top:5px;word-break:break-all;max-width:240px;margin-left:auto;margin-right:auto">${d.scan_url}</p>`;

        connectWS(d.session_id);
    } catch (e) {
        console.error(e);
        toast('Error creating session', true);
    }
}

function closeScanner() {
    document.getElementById('modal').style.display = 'none';
    stopCam();
    if (ws) { ws.close(); ws = null; }
    confirmedPages = {};
    session = null;
}

// ═══ WebSocket ═══

function connectWS(sid) {
    if (ws) ws.close();
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/${sid}/desktop`);
    ws.onopen = () => console.log('[WS] desktop OK');
    ws.onmessage = e => handleMsg(JSON.parse(e.data));
    ws.onclose = () => console.log('[WS] closed');
}

function handleMsg(d) {
    switch (d.type) {
        case 'device_connected':
            if (d.device === 'mobile') {
                setConn(true);
                toast('Mobile connected! 📱');
                setTimeout(() => { localMode = false; goStep(2); }, 800);
            }
            break;

        case 'page_uploaded':
            document.getElementById('remoteCount').textContent = d.total_pages;
            if (d.preview) {
                removeThumb('remoteThumbs', d.page_number);
                addThumb('remoteThumbs', d.preview, d.page_number);
            }
            toast(`Page ${d.page_number} scanned`);
            break;

        case 'page_deleted':
            document.getElementById('remoteCount').textContent = d.total_pages;
            removeThumb('remoteThumbs', d.page_number);
            break;

        case 'pdf_ready':
            goStep(3);
            showPdfResult(d);
            toast('PDF ready! 🎉');
            break;

        case 'device_disconnected':
            if (d.device === 'mobile') { setConn(false); toast('Mobile disconnected', true); }
            break;
    }
}

function setConn(on) {
    const el = document.getElementById('connStatus');
    el.className = `conn-badge ${on ? 'connected' : 'waiting'}`;
    el.innerHTML = on
        ? '<i class="fas fa-check-circle"></i> Mobile connected!'
        : '<i class="fas fa-wifi"></i> Waiting for device...';
}

// ═══ Steps ═══

function goStep(n) {
    ['si1','si2','si3'].forEach((id, i) => {
        const el = document.getElementById(id);
        el.className = 'step' + (i+1 < n ? ' done' : '') + (i+1 === n ? ' active' : '');
    });
    document.getElementById('s1').style.display = n === 1 ? '' : 'none';
    document.getElementById('s2local').style.display = (n === 2 && localMode) ? '' : 'none';
    document.getElementById('s2remote').style.display = (n === 2 && !localMode) ? '' : 'none';
    document.getElementById('s3').style.display = n === 3 ? '' : 'none';
}

// ═══ This Device Camera ═══

async function useThisDevice() {
    localMode = true;
    goStep(2);
    await startCam();
}

async function startCam() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
        });
        document.getElementById('camVideo').srcObject = stream;
    } catch (e) {
        console.error(e);
        toast('Camera not available. Use HTTPS or scan QR with phone.', true);
    }
}

function stopCam() {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    const v = document.getElementById('camVideo');
    if (v) v.srcObject = null;
}

// ═══ Capture (Local) ═══

function captureLocal() {
    if (!session || isUploading) return;
    const v = document.getElementById('camVideo');
    const c = document.getElementById('camCanvas');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0);

    c.toBlob(b => {
        currentBlob = b;
        document.getElementById('previewLocalImg').src = URL.createObjectURL(b);
        document.getElementById('previewLocal').style.display = 'flex';
    }, 'image/jpeg', 0.92);
}

function retakeLocal() {
    document.getElementById('previewLocal').style.display = 'none';
    currentBlob = null;
}

async function acceptLocal() {
    if (!currentBlob || isUploading) return;
    isUploading = true;

    document.getElementById('previewLocal').style.display = 'none';

    const thisPage = pgNum;
    const fd = new FormData();
    fd.append('file', currentBlob, `page_${thisPage}.jpg`);
    fd.append('page_number', thisPage);

    try {
        const r = await fetch(`/api/upload-page/${session.session_id}`, { method: 'POST', body: fd });
        const d = await r.json();

        if (d.status === 'success') {
            // Store confirmed page
            confirmedPages[thisPage] = { preview: d.preview };

            // Update thumbnail (remove old if retake, add new)
            removeThumb('localThumbs', thisPage);
            addThumb('localThumbs', d.preview, thisPage, true);

            pgNum++;
            document.getElementById('pgNum').textContent = pgNum;
            show('finLocalBtn');
            toast(`Page ${thisPage} saved ✓`);
        } else {
            toast('Upload failed', true);
        }
    } catch (e) {
        console.error(e);
        toast('Upload error', true);
    }

    currentBlob = null;
    isUploading = false;
}

async function finishLocal() {
    const count = Object.keys(confirmedPages).length;
    if (count === 0) return toast('Scan at least one page', true);

    stopCam();

    try {
        toast('Generating PDF...');
        const r = await fetch(`/api/finish-scanning/${session.session_id}`, { method: 'POST' });
        const d = await r.json();

        if (d.status === 'success') {
            goStep(3);
            showPdfResult(d);
            toast('PDF ready! 🎉');
        } else {
            toast('Error generating PDF', true);
        }
    } catch (e) {
        console.error(e);
        toast('Error generating PDF', true);
    }
}

// ═══ Thumbnails ═══

function addThumb(cid, src, num, deletable) {
    const c = document.getElementById(cid);
    const t = document.createElement('div');
    t.className = 'thumb';
    t.id = `${cid}-t${num}`;
    t.innerHTML = `<img src="${src}" alt="P${num}"><div class="thumb-num">${num}</div>`
        + (deletable ? `<button class="thumb-del" onclick="event.stopPropagation();delPage(${num},'${cid}')"><i class="fas fa-times"></i></button>` : '');
    c.appendChild(t);
}

function removeThumb(cid, num) {
    const el = document.getElementById(`${cid}-t${num}`);
    if (el) el.remove();
}

async function delPage(num, cid) {
    removeThumb(cid, num);
    delete confirmedPages[num];
    try {
        await fetch(`/api/delete-page/${session.session_id}/${num}`, { method: 'DELETE' });
    } catch (e) { console.error(e); }

    if (Object.keys(confirmedPages).length === 0) hide('finLocalBtn');
}

// ═══ PDF Result ═══

function showPdfResult(d) {
    document.getElementById('pdfInfo').textContent =
        `${d.total_pages} page${d.total_pages > 1 ? 's' : ''} — Enhanced PDF`;

    document.getElementById('dlBtn').href = d.pdf_url;
    document.getElementById('dlBtn').download = d.filename || 'assignment.pdf';

    // PDF preview iframe
    if (d.preview_url || d.pdf_url) {
        const frame = document.getElementById('pdfPreviewFrame');
        frame.src = d.preview_url || d.pdf_url;
        show('pdfPreviewWrap');
    }

    // Page thumbnails
    const rv = document.getElementById('reviewThumbs');
    rv.innerHTML = '';
    if (d.previews && d.previews.length > 0) {
        d.previews.forEach(p => {
            const t = document.createElement('div');
            t.className = 'thumb';
            t.innerHTML = `<img src="${p.src}" alt="P${p.page}"><div class="thumb-num">${p.page}</div>`;
            rv.appendChild(t);
        });
    }
}

async function sharePdf() {
    const url = document.getElementById('dlBtn').href;
    if (navigator.share) {
        try {
            const r = await fetch(url);
            const b = await r.blob();
            await navigator.share({ title: assignment, files: [new File([b], 'assignment.pdf', { type: 'application/pdf' })] });
            return;
        } catch (_) {}
    }
    const full = url.startsWith('http') ? url : location.origin + url;
    navigator.clipboard?.writeText(full);
    toast('Link copied! 📋');
}

async function submitAssignment() {
    if (!session) return;
    const fd = new FormData();
    fd.append('student_name', 'John Smith');
    fd.append('assignment_title', assignment);
    try {
        await fetch(`/api/submit-assignment/${session.session_id}`, { method: 'POST', body: fd });
        toast('Submitted! 🎉');
        setTimeout(closeScanner, 2000);
    } catch (e) { toast('Submit failed', true); }
}

// ═══ Helpers ═══

function show(id) { document.getElementById(id).style.display = ''; }
function hide(id) { document.getElementById(id).style.display = 'none'; }
function clearElement(id) { document.getElementById(id).innerHTML = ''; }

function toast(msg, isError) {
    const t = document.getElementById('toast');
    document.getElementById('toastIcon').className =
        isError ? 'fas fa-exclamation-circle' : 'fas fa-check-circle';
    document.getElementById('toastMsg').textContent = msg;
    t.style.display = 'flex';
    clearTimeout(window._tt);
    window._tt = setTimeout(() => t.style.display = 'none', 3000);
}