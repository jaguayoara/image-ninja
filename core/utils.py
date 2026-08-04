"""Utilidades de ImageNinja."""
from __future__ import annotations

import re
import sys
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Directorio de assets (static/, templates/):
#   - En dev: raiz del proyecto
#   - Empaquetado: dentro de sys._MEIPASS (la carpeta _internal/)
ASSETS_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

# Directorio del usuario (uploads, outputs, models):
#   - En dev: raiz del proyecto
#   - Empaquetado: al lado del .exe (donde el usuario puede escribir)
if getattr(sys, "frozen", False):
    USER_BASE = Path(sys.executable).resolve().parent
else:
    USER_BASE = Path(__file__).resolve().parent.parent

# Alias para retrocompatibilidad con codigo que importa BASE
BASE = USER_BASE

UPLOADS = USER_BASE / "uploads"
OUTPUTS = USER_BASE / "outputs"
MODELS = USER_BASE / "models"
STATIC = ASSETS_BASE / "static"
TEMPLATES = ASSETS_BASE / "templates"

# Limite de subida: 100 MB por imagen
MAX_FILE_SIZE = 100 * 1024 * 1024

# Formatos de imagen soportados
SUPPORTED_INPUT_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
SUPPORTED_OUTPUT_FORMATS = {"png", "jpg", "jpeg", "webp"}

# Catalogo de herramientas
TOOL_INFO = {
    "upscale": {
        "slug": "upscale",
        "name": "Reescalar a 4K",
        "description": "Sube la resolucion de tus imagenes hasta 4K con IA. 100% local.",
        "icon": "sparkles",
    },
    "metadata": {
        "slug": "metadata",
        "name": "Extraer metadatos",
        "description": "Lee EXIF, IPTC, XMP, GPS, camara, lente, fecha, copyright y mas.",
        "icon": "meta",
    },
}


def new_upload_path(filename: str) -> Path:
    """Genera ruta unica en uploads/ y crea el directorio si hace falta."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "upload.bin"
    UPLOADS.mkdir(parents=True, exist_ok=True)
    return UPLOADS / f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}_{safe}"


def new_output_path(stem: str, suffix: str = ".png") -> Path:
    """Genera ruta unica en outputs/ y crea el directorio si hace falta."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", stem) or "output"
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    return OUTPUTS / f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}_{safe}{suffix}"


def download_to_uploads(url: str) -> Path:
    """Descarga una URL a uploads/ y devuelve la ruta."""
    import urllib.request

    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL no valida (debe empezar con http/https)")

    parsed = urlparse(url)
    filename = Path(parsed.path).name or "downloaded"
    dest = new_upload_path(filename)

    req = urllib.request.Request(url, headers={"User-Agent": "ImageNinja/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            f.write(chunk)
    return dest


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"
