# preprocess.py
"""
All preprocessing functions in ONE file.
No fancy classes, just functions. Quick to test.
"""

import cv2
import numpy as np
from typing import Optional, Tuple


# ============================================================
# DOCUMENT DETECTION & PERSPECTIVE CORRECTION
# ============================================================

def order_points(pts):
    """Order 4 points: top-left, top-right, bottom-right, bottom-left"""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def perspective_correct(img, corners):
    """Warp to top-down view given 4 corners"""
    ordered = order_points(corners)
    (tl, tr, br, bl) = ordered

    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(tl - bl), np.linalg.norm(tr - br)))

    # Snap to A4 if close
    aspect = height / width if width > 0 else 1
    if 1.35 < aspect < 1.50:
        height = int(width * 1.414)

    dst = np.array([
        [0, 0], [width-1, 0],
        [width-1, height-1], [0, height-1]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(ordered, dst)
    return cv2.warpPerspective(img, M, (width, height),
                                flags=cv2.INTER_CUBIC,
                                borderMode=cv2.BORDER_REPLICATE)


def detect_document(img):
    """Find document edges and correct perspective. Returns corrected image or original."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    best_contour = None
    best_area = 0
    img_area = img.shape[0] * img.shape[1]

    for canny_low, canny_high in [(30, 100), (50, 150), (75, 200)]:
        edges = cv2.Canny(blurred, canny_low, canny_high)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < img_area * 0.2:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4 and area > best_area:
                best_contour = approx
                best_area = area

    if best_contour is not None:
        return perspective_correct(img, best_contour.reshape(4, 2).astype(np.float32))
    return img


# ============================================================
# DESKEW
# ============================================================

def deskew(img):
    """Fix small rotation using Hough lines"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100,
                             minLineLength=gray.shape[1]//8, maxLineGap=10)
    if lines is None:
        return img

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2-y1, x2-x1))
        if abs(angle) < 15:
            angles.append(angle)

    if not angles:
        return img

    median_angle = np.median(angles)
    if abs(median_angle) < 0.3:
        return img

    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), median_angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


# ============================================================
# GRAYSCALE CONVERSION
# ============================================================

def to_gray(img):
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


# ============================================================
# ILLUMINATION CORRECTION
# ============================================================

def illum_none(img):
    """No illumination correction, just grayscale"""
    return to_gray(img)


def illum_division(img, kernel_size=51):
    """Divide by estimated background"""
    gray = to_gray(img)
    bg = cv2.medianBlur(gray, kernel_size)
    return cv2.divide(gray, bg, scale=255)


def illum_morpho(img, kernel_size=50):
    """Morphological background subtraction"""
    gray = to_gray(img)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    diff = cv2.absdiff(bg, gray)
    normalized = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.bitwise_not(normalized)


def illum_clahe(img, clip_limit=2.0):
    """CLAHE contrast enhancement"""
    gray = to_gray(img)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    return clahe.apply(gray)


def illum_retinex(img, sigma=80):
    """Single-scale retinex"""
    gray = to_gray(img).astype(np.float64) + 1.0
    illumination = cv2.GaussianBlur(gray, (0, 0), sigma)
    retinex = np.log10(gray) - np.log10(illumination)
    result = cv2.normalize(retinex, None, 0, 255, cv2.NORM_MINMAX)
    return result.astype(np.uint8)


# ============================================================
# BINARIZATION
# ============================================================

def bin_none(gray):
    """No binarization — pass through grayscale"""
    return gray


def bin_otsu(gray):
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def bin_adaptive_gaussian(gray, block=11, C=2):
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, block, C)


def bin_adaptive_mean(gray, block=15, C=5):
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, block, C)


def bin_sauvola(gray, window_size=25, k=0.2):
    """Sauvola — best for handwritten text"""
    mean = cv2.blur(gray.astype(np.float64), (window_size, window_size))
    sq_mean = cv2.blur((gray.astype(np.float64))**2, (window_size, window_size))
    std = np.sqrt(np.maximum(sq_mean - mean**2, 0))
    threshold = mean * (1.0 + k * (std / 128.0 - 1.0))
    binary = np.zeros_like(gray)
    binary[gray > threshold] = 255
    return binary


# ============================================================
# QUALITY METRICS
# ============================================================

def measure_quality(img):
    """Quick quality metrics for any image"""
    gray = to_gray(img) if len(img.shape) == 3 else img

    metrics = {}
    metrics['resolution'] = f"{img.shape[1]}x{img.shape[0]}"
    metrics['blur_score'] = round(cv2.Laplacian(gray, cv2.CV_64F).var(), 2)
    metrics['brightness'] = round(float(np.mean(gray)), 2)
    metrics['contrast'] = round(float(np.std(gray)), 2)

    h, w = gray.shape
    region_means = []
    for i in range(3):
        for j in range(3):
            region = gray[i*h//3:(i+1)*h//3, j*w//3:(j+1)*w//3]
            region_means.append(np.mean(region))
    overall_mean = np.mean(region_means)
    metrics['uniformity'] = round(1.0 - (np.std(region_means) / max(overall_mean, 1)), 3)

    return metrics