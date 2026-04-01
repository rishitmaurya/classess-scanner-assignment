"""
═══════════════════════════════════════════════════════════════
  CV PROCESSOR — Perspective Crop + High Quality Output
  
  The client sends corner points, server applies transform
═══════════════════════════════════════════════════════════════
"""

import cv2
import numpy as np
import base64
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import config

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=4)


# ═══════════════════════════════════════════════════════════
#  PERSPECTIVE TRANSFORM
# ═══════════════════════════════════════════════════════════

def order_points(pts: np.ndarray) -> np.ndarray:
    """Order points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]      # top-left
    rect[2] = pts[np.argmax(s)]      # bottom-right
    rect[1] = pts[np.argmin(d)]      # top-right
    rect[3] = pts[np.argmax(d)]      # bottom-left
    return rect


def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply perspective transform to get a top-down view."""
    rect = order_points(pts)
    tl, tr, br, bl = rect

    # Compute new width
    w1 = np.linalg.norm(br - bl)
    w2 = np.linalg.norm(tr - tl)
    max_w = max(int(w1), int(w2))

    # Compute new height
    h1 = np.linalg.norm(tr - br)
    h2 = np.linalg.norm(tl - bl)
    max_h = max(int(h1), int(h2))

    # Ensure minimum size
    max_w = max(max_w, 100)
    max_h = max(max_h, 100)

    dst = np.array([
        [0, 0],
        [max_w - 1, 0],
        [max_w - 1, max_h - 1],
        [0, max_h - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    # Use INTER_LANCZOS4 for highest quality
    return cv2.warpPerspective(image, M, (max_w, max_h), flags=cv2.INTER_LANCZOS4)


# ═══════════════════════════════════════════════════════════
#  DOCUMENT DETECTION (for API endpoint)
# ═══════════════════════════════════════════════════════════

def detect_document_corners(image_bytes: bytes) -> Optional[List[List[float]]]:
    """
    Detect document corners in image.
    Returns [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] as percentages (0-1).
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None
    
    h, w = img.shape[:2]
    
    # Resize for faster processing
    max_dim = 500
    scale = min(max_dim / max(h, w), 1.0)
    if scale < 1.0:
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = img
    
    corners = _find_document(small)
    
    if corners is not None:
        # Scale back and convert to percentages
        corners = corners / scale
        corners_pct = []
        for pt in corners:
            corners_pct.append([float(pt[0]) / w, float(pt[1]) / h])
        return corners_pct
    
    # Default: return full image corners with small margin
    margin = 0.02
    return [
        [margin, margin],
        [1 - margin, margin],
        [1 - margin, 1 - margin],
        [margin, 1 - margin]
    ]


def _find_document(image: np.ndarray) -> Optional[np.ndarray]:
    """Find document rectangle in image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    img_area = h * w
    
    # Try multiple methods
    for method in [_method_canny, _method_adaptive, _method_color, _method_morph]:
        try:
            result = method(image, gray, img_area)
            if result is not None and _validate_quad(result, img_area):
                return result
        except:
            continue
    
    return None


def _method_canny(image, gray, img_area):
    """Canny edge detection."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = np.median(blurred)
    edges = cv2.Canny(blurred, int(0.5 * median), int(1.5 * median))
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=2)
    return _find_largest_quad(edges, img_area)


def _method_adaptive(image, gray, img_area):
    """Adaptive threshold."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 11, 2)
    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    return _find_largest_quad(thresh, img_area)


def _method_color(image, gray, img_area):
    """Color-based detection (white paper)."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    _, thresh = cv2.threshold(l_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    white_ratio = np.sum(thresh == 255) / thresh.size
    if white_ratio < 0.3:
        thresh = cv2.bitwise_not(thresh)
    
    kernel = np.ones((7, 7), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    return _find_largest_quad(thresh, img_area)


def _method_morph(image, gray, img_area):
    """Morphological approach."""
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((9, 9), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
    return _find_largest_quad(thresh, img_area)


def _find_largest_quad(binary, img_area):
    """Find largest quadrilateral in binary image."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.1:
            continue
        
        peri = cv2.arcLength(cnt, True)
        for eps in [0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(cnt, eps * peri, True)
            if len(approx) == 4:
                return approx.reshape(4, 2).astype("float32")
        
        # Fallback to bounding rect
        if area > img_area * 0.15:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            return box.astype("float32")
    
    return None


def _validate_quad(quad, img_area):
    """Validate quadrilateral."""
    if quad is None or len(quad) != 4:
        return False
    area = cv2.contourArea(quad.astype(np.int32))
    return img_area * 0.05 < area < img_area * 0.98


# ═══════════════════════════════════════════════════════════
#  MAIN PROCESSING — WITH CORNER POINTS
# ═══════════════════════════════════════════════════════════

def process_document_with_corners(image_bytes: bytes, corners: List[List[float]]) -> bytes:
    """
    Process document image with user-specified corner points.
    
    Args:
        image_bytes: Raw image bytes
        corners: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] as percentages (0-1)
    
    Returns:
        Cropped and transformed image as high-quality JPEG bytes
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        print("[CV] Could not decode image")
        return image_bytes
    
    h, w = img.shape[:2]
    print(f"  [process] Input: {w}x{h}")
    
    # Convert percentage corners to pixel coordinates
    pts = np.array([
        [corners[0][0] * w, corners[0][1] * h],
        [corners[1][0] * w, corners[1][1] * h],
        [corners[2][0] * w, corners[2][1] * h],
        [corners[3][0] * w, corners[3][1] * h],
    ], dtype="float32")
    
    # Apply perspective transform
    cropped = four_point_transform(img, pts)
    
    ch, cw = cropped.shape[:2]
    print(f"  [process] Cropped: {cw}x{ch}")
    
    # High quality encode
    quality = getattr(config, 'CV_JPEG_QUALITY', 95)
    _, buf = cv2.imencode('.jpg', cropped, [
        cv2.IMWRITE_JPEG_QUALITY, quality,
        cv2.IMWRITE_JPEG_OPTIMIZE, 1
    ])
    
    result = buf.tobytes()
    print(f"  [process] Output: {len(result) // 1024}KB")
    
    return result


def enhance_document_image(image_bytes: bytes) -> bytes:
    """
    Fallback: process without corner points (auto-detect or full image).
    """
    corners = detect_document_corners(image_bytes)
    if corners:
        return process_document_with_corners(image_bytes, corners)
    
    # No detection, return re-encoded original
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes
    
    quality = getattr(config, 'CV_JPEG_QUALITY', 95)
    _, buf = cv2.imencode('.jpg', img, [
        cv2.IMWRITE_JPEG_QUALITY, quality,
        cv2.IMWRITE_JPEG_OPTIMIZE, 1
    ])
    return buf.tobytes()


# ═══════════════════════════════════════════════════════════
#  PDF GENERATION
# ═══════════════════════════════════════════════════════════

def get_page_size():
    return {"A4": A4, "LETTER": letter}.get(config.PDF_PAGE_SIZE.upper(), A4)


def create_pdf_from_images(image_paths: List[str], output_path: str) -> str:
    """Create high quality PDF from images."""
    page_size = get_page_size()
    c = canvas.Canvas(output_path, pagesize=page_size)
    pw, ph = page_size
    margin = config.PDF_MARGIN

    for path in image_paths:
        try:
            pil = Image.open(path)
            if pil.mode not in ('RGB', 'RGBA'):
                pil = pil.convert('RGB')

            iw, ih = pil.size
            aw, ah = pw - 2 * margin, ph - 2 * margin
            scale = min(aw / iw, ah / ih)
            nw, nh = iw * scale, ih * scale

            x = margin + (aw - nw) / 2
            y = margin + (ah - nh) / 2

            c.drawImage(ImageReader(pil), x, y, nw, nh, preserveAspectRatio=True)
            c.showPage()
        except Exception as e:
            print(f"[PDF] Error: {e}")

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════
#  PREVIEW
# ═══════════════════════════════════════════════════════════

def make_preview_b64(image_bytes: bytes, max_w: int = 300) -> str:
    """Generate base64 preview thumbnail."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return ""

    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)

    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf.tobytes()).decode()