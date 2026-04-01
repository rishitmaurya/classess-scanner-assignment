"""
═══════════════════════════════════════════════════════════════
  CV PROCESSOR — Simple capture-to-PDF
  
  No image processing. Just:
    - Accept captured images as-is
    - Combine into PDF
    - Generate previews
═══════════════════════════════════════════════════════════════
"""

import cv2
import numpy as np
import base64
from typing import List

from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import config


# ═══════════════════════════════════════════════════════════
#  MAIN ENTRY — NO PROCESSING, JUST PASS THROUGH
# ═══════════════════════════════════════════════════════════

def enhance_document_image(image_bytes: bytes) -> bytes:
    """
    Accept image bytes and return them as-is (JPEG re-encoded).
    No CV processing — just clean passthrough.
    """
    # Decode to validate it's a real image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        print("[CV] WARNING: Could not decode image, returning raw bytes")
        return image_bytes

    # Re-encode as JPEG (normalizes format, strips metadata)
    quality = getattr(config, 'CV_JPEG_QUALITY', 92)
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


# ═══════════════════════════════════════════════════════════
#  PDF GENERATION
# ═══════════════════════════════════════════════════════════

def get_page_size():
    """Get configured PDF page size."""
    return {"A4": A4, "LETTER": letter}.get(config.PDF_PAGE_SIZE.upper(), A4)


def create_pdf_from_images(image_paths: List[str], output_path: str) -> str:
    """
    Create PDF from list of image paths.
    Each image centered on page, scaled to fit with margins.
    """
    page_size = get_page_size()
    c = canvas.Canvas(output_path, pagesize=page_size)
    pw, ph = page_size
    margin = config.PDF_MARGIN

    for path in image_paths:
        try:
            pil = Image.open(path)

            # Ensure RGB for PDF
            if pil.mode == 'L':
                pil = pil.convert('RGB')
            elif pil.mode not in ('RGB', 'RGBA'):
                pil = pil.convert('RGB')

            # Scale to fit page
            iw, ih = pil.size
            aw, ah = pw - 2 * margin, ph - 2 * margin
            scale = min(aw / iw, ah / ih)
            nw, nh = iw * scale, ih * scale

            # Center on page
            x = margin + (aw - nw) / 2
            y = margin + (ah - nh) / 2

            c.drawImage(ImageReader(pil), x, y, nw, nh,
                        preserveAspectRatio=True)
            c.showPage()

        except Exception as e:
            print(f"[PDF] Error adding {path}: {e}")

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════
#  PREVIEW GENERATION
# ═══════════════════════════════════════════════════════════

def make_preview_b64(image_bytes: bytes, max_w: int = 300) -> str:
    """Generate base64-encoded JPEG thumbnail for UI preview."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return ""

    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, int(h * max_w / w)))

    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf.tobytes()).decode()