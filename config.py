"""
All configuration in one place.
"""

# ─── SERVER ───
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
DEBUG = True

# ─── PATHS ───
UPLOAD_DIR = "uploads"
SCANS_DIR = "uploads/scans"
PDFS_DIR = "uploads/pdfs"
STATIC_DIR = "static"
TEMPLATES_DIR = "templates"

# ─── CORS ───
CORS_ORIGINS = ["*"]
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]

# ─── TUNNEL ───
NGROK_ENABLED = True
CLOUDFLARE_ENABLED = False
NGROK_AUTH_TOKEN = ""  # https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_REGION = "in"
NGROK_DOMAIN = ""
MANUAL_PUBLIC_URL = ""

# ─── CV SETTINGS ───
# Pipeline: detect_document → illum_division → bin_sauvola
CV_JPEG_QUALITY = 95
CV_DESKEW_MAX_ANGLE = 15

# Sauvola binarization params
CV_SAUVOLA_WINDOW = 0   # 0 = auto-calculate from image size
CV_SAUVOLA_K = 0.2      # sensitivity (lower = more text preserved)
CV_SAUVOLA_R = 128.0    # dynamic range

# CLAHE (used if you switch to clahe illumination)
CV_CLAHE_CLIP = 1.5

# ─── PDF ───
PDF_PAGE_SIZE = "A4"
PDF_MARGIN = 36

# ─── ROUTES ───
ROUTE_HOME = "/"
ROUTE_SCAN = "/scan/{session_id}"
ROUTE_CREATE_SESSION = "/api/create-session"
ROUTE_UPLOAD_PAGE = "/api/upload-page/{session_id}"
ROUTE_DELETE_PAGE = "/api/delete-page/{session_id}/{page_number}"
ROUTE_FINISH = "/api/finish-scanning/{session_id}"
ROUTE_DOWNLOAD = "/api/download-pdf/{session_id}"
ROUTE_PREVIEW = "/api/preview-pdf/{session_id}"
ROUTE_SESSION_STATUS = "/api/session-status/{session_id}"
ROUTE_SUBMIT = "/api/submit-assignment/{session_id}"
ROUTE_SET_URL = "/api/set-public-url"
ROUTE_GET_URL = "/api/get-public-url"
ROUTE_DETECT_TUNNEL = "/api/detect-tunnel"
ROUTE_WS = "/ws/{session_id}/{device_type}"

# ─── SESSION ───
SESSION_ID_LENGTH = 8
SESSION_EXPIRY_MINUTES = 60

# ─── QR ───
QR_BOX_SIZE = 10
QR_BORDER = 4
QR_FILL_COLOR = "black"
QR_BACK_COLOR = "white"