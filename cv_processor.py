"""
═══════════════════════════════════════════════════════════════
  CV PROCESSOR — "Balanced" Pipeline + White Background Cleanup
  
  Pipeline: detect_document → illum_division → bin_sauvola → cleanup
═══════════════════════════════════════════════════════════════
"""

import cv2
import numpy as np
import base64
import math
from typing import List, Optional, Tuple
from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import config


# ═══════════════════════════════════════════════════════════
#  MAIN ENTRY POINT (MODIFIED — added cleanup step)
# ═══════════════════════════════════════════════════════════

def enhance_document_image(image_bytes: bytes) -> bytes:
    """
    Pipeline:
      1. detect_document  — find & extract paper
      2. illum_division   — normalize illumination
      3. bin_sauvola      — local adaptive binarization
      4. cleanup_binary   — force pure white bg, remove edge noise
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    try:
        # Step 1: Detect and extract document
        img = detect_document(img)

        # Step 2: Illumination normalization (division method)
        gray = illum_division(img)

        # Step 3: Sauvola binarization
        binary = bin_sauvola(gray)

        # Step 4: Cleanup — pure white background, remove noise
        result = cleanup_binary(binary)

    except Exception as e:
        print(f"[CV] Pipeline error: {e}, attempting fallback")
        try:
            nparr2 = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)
            img = detect_document(img)
            gray = illum_division(img)
            result = bin_sauvola(gray)
            result = cleanup_binary(result)
        except Exception:
            nparr2 = np.frombuffer(image_bytes, np.uint8)
            result = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)

    # Encode
    _, buf = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, config.CV_JPEG_QUALITY])
    return buf.tobytes()


# ═══════════════════════════════════════════════════════════
#  STEP 4: CLEANUP — PURE WHITE BACKGROUND (NEW)
# ═══════════════════════════════════════════════════════════

def cleanup_binary(binary: np.ndarray) -> np.ndarray:
    """
    Post-binarization cleanup to ensure:
    1. Background is PURE white (255)
    2. Text/ink is clean black
    3. Small noise specks removed
    4. Edge artifacts from page binding cleaned
    """
    if len(binary.shape) == 3:
        binary = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)

    h, w = binary.shape[:2]

    # ── 1. Force pure black and white ──
    # Sauvola sometimes produces near-white (250-254) or near-black (1-10)
    # Force everything to pure 0 or 255
    _, clean = cv2.threshold(binary, 127, 255, cv2.THRESH_BINARY)

    # ── 2. Remove small noise (tiny black specks in white areas) ──
    # These are dust, paper texture artifacts, etc.
    # Use morphological opening (erode then dilate)
    noise_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, noise_kernel, iterations=1)

    # ── 3. Remove small isolated black components (noise) ──
    # Find all connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        cv2.bitwise_not(clean), connectivity=8
    )

    # Calculate minimum area for a real text stroke
    # Very small components are noise
    min_area = max(8, (h * w) // 50000)  # adaptive based on image size

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area:
            # This component is too small — it's noise, make it white
            clean[labels == i] = 255

    # ── 4. Clean page edges ──
    # Often the page binding, folded corners, or shadow at edges
    # creates dark artifacts. Clean a thin border.
    border = max(3, min(h, w) // 200)  # adaptive border size
    clean[:border, :] = 255      # top
    clean[-border:, :] = 255     # bottom
    clean[:, :border] = 255      # left
    clean[:, -border:] = 255     # right

    # ── 5. Fill small holes in text strokes ──
    # Sometimes binarization creates tiny white holes inside black strokes
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, close_kernel, iterations=1)

    # ── 6. Final force to pure B&W ──
    _, clean = cv2.threshold(clean, 127, 255, cv2.THRESH_BINARY)

    return clean


# ═══════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════

def to_gray(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 2:
        return img
    if img.shape[2] == 1:
        return img[:, :, 0]
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def measure_quality(img: np.ndarray) -> dict:
    gray = to_gray(img) if len(img.shape) == 3 else img
    contrast = float(gray.std())
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blurred = cv2.GaussianBlur(gray, (51, 51), 0)
    uniformity = 1.0 - float(blurred.std()) / 128.0
    uniformity = max(0.0, min(1.0, uniformity))
    return {'contrast': contrast, 'blur_score': blur_score, 'uniformity': uniformity}


# ═══════════════════════════════════════════════════════════
#  STEP 1: DOCUMENT DETECTION (unchanged)
# ═══════════════════════════════════════════════════════════

def detect_document(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        return img

    original = img.copy()
    h, w = img.shape[:2]
    best_quad = None
    best_area = 0

    max_dim = 1000
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = img.copy()

    sh, sw = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Strategy 1: Canny edges
    for blur_k in [5, 7]:
        blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
        for canny_lo, canny_hi in [(30, 100), (50, 150), (20, 80), (75, 200)]:
            edges = cv2.Canny(blurred, canny_lo, canny_hi)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            edges = cv2.dilate(edges, kernel, iterations=2)
            edges = cv2.erode(edges, kernel, iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            quad = _find_best_quad(contours, sh, sw)
            if quad is not None:
                area = cv2.contourArea(quad)
                if area > best_area and area > sh * sw * 0.15:
                    best_area = area
                    best_quad = quad

    # Strategy 2: Adaptive threshold
    if best_quad is None or best_area < sh * sw * 0.25:
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 51, 10)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        quad = _find_best_quad(contours, sh, sw)
        if quad is not None:
            area = cv2.contourArea(quad)
            if area > best_area and area > sh * sw * 0.15:
                best_area = area
                best_quad = quad

    # Strategy 3: Color-based
    if best_quad is None or best_area < sh * sw * 0.25:
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        paper_mask = cv2.inRange(hsv, (0, 0, 120), (180, 80, 255))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_CLOSE, kernel, iterations=4)
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_OPEN, kernel, iterations=2)
        contours, _ = cv2.findContours(paper_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        quad = _find_best_quad(contours, sh, sw)
        if quad is not None:
            area = cv2.contourArea(quad)
            if area > best_area and area > sh * sw * 0.15:
                best_area = area
                best_quad = quad

    if best_quad is not None:
        pts = best_quad.reshape(4, 2).astype("float32") / scale
        warped = _four_point_transform(original, pts)
        wh, ww = warped.shape[:2]
        if wh > 100 and ww > 100:
            return warped

    return original


def _find_best_quad(contours, img_h, img_w) -> Optional[np.ndarray]:
    if not contours:
        return None
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for cnt in contours[:10]:
        area = cv2.contourArea(cnt)
        if area < img_h * img_w * 0.1:
            continue
        peri = cv2.arcLength(cnt, True)
        for eps_mult in [0.02, 0.03, 0.04, 0.05, 0.06, 0.08]:
            approx = cv2.approxPolyDP(cnt, eps_mult * peri, True)
            if len(approx) == 4:
                if cv2.isContourConvex(approx):
                    return approx
        if area > img_h * img_w * 0.2:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            return np.int0(box)
    return None


def _four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxW = max(int(widthA), int(widthB))
    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxH = max(int(heightA), int(heightB))
    if maxW < 100 or maxH < 100:
        return image
    dst = np.array([[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]],
                    dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxW, maxH),
                                  flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return warped


def _order_points(pts: np.ndarray) -> np.ndarray:
    pts = pts.astype("float32")
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


# ═══════════════════════════════════════════════════════════
#  STEP 2: ILLUMINATION — DIVISION (unchanged)
# ═══════════════════════════════════════════════════════════

def illum_division(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    gray = gray.astype(np.float32)
    h, w = gray.shape[:2]
    ksize = max(h, w) // 5
    if ksize % 2 == 0:
        ksize += 1
    ksize = max(ksize, 51)
    ksize = min(ksize, 301)

    bg = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    bg = np.maximum(bg, 1.0)
    result = (gray / bg) * 255.0
    result = cv2.normalize(result, None, 0, 255, cv2.NORM_MINMAX)
    return result.astype(np.uint8)


# ═══════════════════════════════════════════════════════════
#  STEP 3: BINARIZATION — SAUVOLA (unchanged)
# ═══════════════════════════════════════════════════════════

def bin_sauvola(gray: np.ndarray, window_size: int = 0, k: float = 0.2,
                R: float = 128.0) -> np.ndarray:
    if len(gray.shape) == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    gray = gray.astype(np.float64)

    if window_size <= 0:
        h, w = gray.shape[:2]
        window_size = max(h, w) // 30
        if window_size % 2 == 0:
            window_size += 1
        window_size = max(window_size, 15)
        window_size = min(window_size, 101)

    mean = cv2.blur(gray, (window_size, window_size))
    mean_sq = cv2.blur(gray ** 2, (window_size, window_size))
    variance = mean_sq - mean ** 2
    variance = np.maximum(variance, 0)
    std = np.sqrt(variance)

    threshold = mean * (1.0 + k * (std / R - 1.0))

    binary = np.zeros_like(gray, dtype=np.uint8)
    binary[gray >= threshold] = 255

    return binary


# ═══════════════════════════════════════════════════════════
#  ADDITIONAL METHODS (kept for flexibility)
# ═══════════════════════════════════════════════════════════

def illum_none(img):
    return img

def illum_morpho(img):
    gray = to_gray(img) if len(img.shape) == 3 else img
    gray = gray.astype(np.float32)
    h, w = gray.shape[:2]
    ksize = max(h, w) // 10
    if ksize % 2 == 0: ksize += 1
    ksize = max(ksize, 51)
    ksize = min(ksize, 201)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    bg = cv2.morphologyEx(gray.astype(np.uint8), cv2.MORPH_OPEN, kernel).astype(np.float32)
    bg = np.maximum(bg, 1.0)
    result = (gray / bg) * 255.0
    result = cv2.normalize(result, None, 0, 255, cv2.NORM_MINMAX)
    return result.astype(np.uint8)

def illum_clahe(img):
    gray = to_gray(img) if len(img.shape) == 3 else img
    clahe = cv2.createCLAHE(clipLimit=config.CV_CLAHE_CLIP, tileGridSize=(8, 8))
    return clahe.apply(gray)

def illum_retinex(img):
    gray = to_gray(img) if len(img.shape) == 3 else img
    gray = gray.astype(np.float64) + 1.0
    scales = [15, 80, 250]
    retinex = np.zeros_like(gray)
    for sigma in scales:
        blur = cv2.GaussianBlur(gray, (0, 0), sigma)
        blur = np.maximum(blur, 1.0)
        retinex += np.log(gray) - np.log(blur)
    retinex /= len(scales)
    retinex = cv2.normalize(retinex, None, 0, 255, cv2.NORM_MINMAX)
    return retinex.astype(np.uint8)

def bin_none(gray):
    return to_gray(gray) if len(gray.shape) == 3 else gray

def bin_otsu(gray):
    gray = to_gray(gray) if len(gray.shape) == 3 else gray
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def bin_adaptive_gaussian(gray):
    gray = to_gray(gray) if len(gray.shape) == 3 else gray
    h, w = gray.shape[:2]
    block = max(h, w) // 30
    if block % 2 == 0: block += 1
    block = max(block, 11)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, block, 8)

def bin_adaptive_mean(gray):
    gray = to_gray(gray) if len(gray.shape) == 3 else gray
    h, w = gray.shape[:2]
    block = max(h, w) // 30
    if block % 2 == 0: block += 1
    block = max(block, 11)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, block, 8)


def deskew(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    gray = to_gray(img)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 8, 30), 1))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    lines = cv2.HoughLinesP(dilated, 1, np.pi / 180, threshold=100,
                             minLineLength=w * 0.15, maxLineGap=30)
    if lines is None or len(lines) < 3:
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) > 500:
            angle = cv2.minAreaRect(coords)[-1]
            angle = -(90 + angle) if angle < -45 else -angle
        else:
            return img
    else:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) > 10:
                a = math.degrees(math.atan2(y2 - y1, x2 - x1))
                if abs(a) < 30:
                    angles.append(a)
        if not angles:
            return img
        angle = float(np.median(angles))

    if abs(angle) < 0.3 or abs(angle) > config.CV_DESKEW_MAX_ANGLE:
        return img

    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2
    rotated = cv2.warpAffine(img, M, (new_w, new_h), flags=cv2.INTER_CUBIC,
                              borderValue=(255, 255, 255) if len(img.shape) == 3 else 255)
    return rotated


# ═══════════════════════════════════════════════════════════
#  PDF GENERATION
# ═══════════════════════════════════════════════════════════

def get_page_size():
    return {"A4": A4, "LETTER": letter}.get(config.PDF_PAGE_SIZE.upper(), A4)


def create_pdf_from_images(image_paths: List[str], output_path: str) -> str:
    page_size = get_page_size()
    c = canvas.Canvas(output_path, pagesize=page_size)
    pw, ph = page_size
    margin = config.PDF_MARGIN

    for path in image_paths:
        try:
            pil = Image.open(path)
            if pil.mode == 'L':
                pil = pil.convert('RGB')
            elif pil.mode not in ('RGB', 'RGBA'):
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
            print(f"[PDF] Error {path}: {e}")
    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════
#  PREVIEW
# ═══════════════════════════════════════════════════════════

def make_preview_b64(image_bytes: bytes, max_w: int = 300) -> str:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return ""
    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, int(h * max_w / w)))
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf.tobytes()).decode()