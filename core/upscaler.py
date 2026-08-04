"""
Core de ImageNinja - reescalado y mejora de imagenes.

Modos disponibles:
  - lanczos        : filtro clasico, rapido, 100% offline, sin modelo
  - realesrgan     : IA Real-ESRGAN, maxima calidad, requiere modelo
  - best           : pipeline de maxima calidad (denoise + IA + sharpen + Lanczos)

El modelo Real-ESRGAN NO se incluye en el repo. Si el usuario quiere usarlo,
se descarga automaticamente al startup desde el repo oficial de xinntao.
"""
from __future__ import annotations

import io
import logging
import urllib.request
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageFilter

log = logging.getLogger("imageninja.core")

# Modelos de IA soportados
REALESRGAN_MODELS = {
    "realesrgan-x4plus": {
        "file": "RealESRGAN_x4plus.pth",
        "scale": 4,
        "description": "Real-ESRGAN x4 (fotos reales, mejor calidad)",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "size_mb": 64,
    },
    "realesrgan-x2plus": {
        "file": "RealESRGAN_x2plus.pth",
        "scale": 2,
        "description": "Real-ESRGAN x2 (mas rapido)",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "size_mb": 64,
    },
    "realesrgan-anime": {
        "file": "RealESRGAN_x4plus_anime_6B.pth",
        "scale": 4,
        "description": "Real-ESRGAN anime (ilustraciones)",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "size_mb": 18,
    },
}

DEFAULT_MODEL = "realesrgan-x4plus"

# Resoluciones 4K conocidas
RESOLUTIONS_4K = {
    "4k_uhd": (3840, 2160),
    "4k_dci": (4096, 2160),
    "qhd":    (2560, 1440),
}


# -----------------------------------------------------------------------------
# Auto-descarga del modelo
# -----------------------------------------------------------------------------
def ensure_model(model_name: str = DEFAULT_MODEL, progress_cb=None) -> Optional[Path]:
    """Asegura que el modelo este descargado. Devuelve la ruta o None.

    Si progress_cb esta definido, se llama con (bytes_descargados, total_bytes).
    """
    from . import utils
    info = REALESRGAN_MODELS[model_name]
    model_path = utils.MODELS / info["file"]
    if model_path.exists() and model_path.stat().st_size > 1_000_000:
        return model_path

    utils.MODELS.mkdir(parents=True, exist_ok=True)
    log.info("Descargando modelo %s (~%d MB)...", info["file"], info["size_mb"])

    url = info["url"]
    req = urllib.request.Request(url, headers={"User-Agent": "ImageNinja/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk_size = 1024 * 256  # 256 KB
        with open(model_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded, total)
    log.info("Modelo descargado: %s (%.1f MB)", model_path, model_path.stat().st_size / 1_000_000)
    return model_path


# -----------------------------------------------------------------------------
# API publica
# -----------------------------------------------------------------------------
def image_info(path: Path) -> dict:
    """Devuelve metadata de la imagen."""
    img = Image.open(path)
    w, h = img.size
    return {
        "filename": path.name,
        "width": w,
        "height": h,
        "mode": img.mode,
        "format": img.format,
        "size_bytes": path.stat().st_size,
        "size_human": _human_size(path.stat().st_size),
        "megapixels": round((w * h) / 1_000_000, 2),
    }


def upscale(src: Path, dst: Path, method: str, scale: float, target: Optional[str],
            output_format: str, quality: int, model_cache: dict,
            progress_cb=None) -> dict:
    """Reescala la imagen. Devuelve dict con metadata del resultado.

    Methods:
      - lanczos: rapido, sin IA
      - realesrgan: IA pura
      - best: pipeline completa (denoise + IA + sharpen + Lanczos refine)
    """
    method = (method or "lanczos").lower()
    if method == "best":
        return _upscale_best(src, dst, scale, target, output_format, quality, model_cache, progress_cb)
    if method == "realesrgan":
        return _upscale_realesrgan(src, dst, scale, target, output_format, quality, model_cache)
    return _upscale_lanczos(src, dst, scale, target, output_format, quality)


def realesrgan_available() -> bool:
    """True si la libreria y el modelo estan listos."""
    if not _realesrgan_importable():
        return False
    model_path = _default_model_path()
    return model_path is not None and model_path.exists()


def model_status() -> dict:
    """Estado del modelo: si esta, si esta descargandose, etc."""
    from . import utils
    info = REALESRGAN_MODELS[DEFAULT_MODEL]
    path = utils.MODELS / info["file"]
    return {
        "model": DEFAULT_MODEL,
        "filename": info["file"],
        "exists": path.exists(),
        "size_mb": round(path.stat().st_size / 1_000_000, 1) if path.exists() else 0,
        "expected_mb": info["size_mb"],
        "url": info["url"],
        "description": info["description"],
        "deps_ok": _realesrgan_importable(),
    }


# -----------------------------------------------------------------------------
# Lanczos (Pillow) - rapido, sin IA
# -----------------------------------------------------------------------------
def _upscale_lanczos(src: Path, dst: Path, scale: float, target: Optional[str],
                     output_format: str, quality: int) -> dict:
    img = Image.open(src).convert("RGB")
    w0, h0 = img.size
    w1, h1 = _compute_target_size(w0, h0, scale, target)

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    if (w1, h1) != (w0, h0):
        img = img.resize((w1, h1), resample=resample, reducing_gap=3)

    _save_image(img, dst, output_format, quality)

    return {
        "path": str(dst),
        "filename": dst.name,
        "filename_original": src.name,
        "width": w1,
        "height": h1,
        "width_original": w0,
        "height_original": h0,
        "scale_factor": round(w1 / w0, 2),
        "method": "lanczos",
        "size_bytes": dst.stat().st_size,
    }


# -----------------------------------------------------------------------------
# Best quality - denoise + Real-ESRGAN + sharpen + Lanczos refine
# -----------------------------------------------------------------------------
def _upscale_best(src: Path, dst: Path, scale: float, target: Optional[str],
                  output_format: str, quality: int, model_cache: dict,
                  progress_cb=None) -> dict:
    """Pipeline de maxima calidad.

    1. Denoise suave (Pillow MedianFilter) - quita ruido para que la IA no lo amplifique
    2. Real-ESRGAN - super-resolucion IA
    3. UnsharpMask - recuperacion de nitidez
    4. Si el target excede lo que la IA puede dar, hace una pasada Lanczos al final
    """
    if progress_cb: progress_cb(5, 100, "Etapa 1/4: Denoise")
    log.info("[best] Step 1/4: Denoise")
    img = Image.open(src).convert("RGB")
    w0, h0 = img.size
    img = _denoise(img)

    # Calculamos tamano final
    w1, h1 = _compute_target_size(w0, h0, scale, target)

    # Si la IA esta disponible, la usamos
    if realesrgan_available():
        if progress_cb: progress_cb(15, 100, "Etapa 2/4: Real-ESRGAN")
        log.info("[best] Step 2/4: Real-ESRGAN upscale")
        upsampler = _get_upsampler(DEFAULT_MODEL, model_cache)
        try:
            import numpy as np
            arr = np.array(img)
            # Una sola pasada a 4x nativo (el modelo es x4plus).
            # Para targets > 4x, hacemos una pasada IA + Lanczos al final.
            # Multiples pasadas de IA pueden romper por temas de tile size.
            out, _ = upsampler.enhance(arr, outscale=upsampler.scale)
            img = Image.fromarray(out)
            log.info("[best] Real-ESRGAN: %dx%d -> %dx%d",
                     arr.shape[1], arr.shape[0], img.size[0], img.size[1])
        except Exception as e:
            log.warning("[best] Real-ESRGAN fallo (%s), fallback a Lanczos", e)
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img = img.resize((w1, h1), resample=resample, reducing_gap=3)
    else:
        # IA no disponible -> usar Lanczos al tamano objetivo
        if progress_cb: progress_cb(30, 100, "Etapa 2/4: Lanczos (IA no disponible)")
        log.info("[best] Real-ESRGAN no disponible, fallback a Lanczos")
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img = img.resize((w1, h1), resample=resample, reducing_gap=3)

    # Paso 3: ajustar al tamano final exacto y sharpen
    if progress_cb: progress_cb(70, 100, "Etapa 3/4: Refinamiento y sharpen")
    log.info("[best] Step 3/4: Ajuste a tamano final + sharpen")
    if img.size != (w1, h1):
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img = img.resize((w1, h1), resample=resample, reducing_gap=3)
    img = _sharpen(img)

    if progress_cb: progress_cb(90, 100, "Etapa 4/4: Guardando")
    log.info("[best] Step 4/4: Guardando")
    _save_image(img, dst, output_format, quality)

    return {
        "path": str(dst),
        "filename": dst.name,
        "filename_original": src.name,
        "width": w1,
        "height": h1,
        "width_original": w0,
        "height_original": h0,
        "scale_factor": round(w1 / w0, 2),
        "method": "best",
        "size_bytes": dst.stat().st_size,
    }


# -----------------------------------------------------------------------------
# Real-ESRGAN (IA) - simple upscale
# -----------------------------------------------------------------------------
def _realesrgan_importable() -> bool:
    try:
        import basicsr  # noqa: F401
        import realesrgan  # noqa: F401
        import torch  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _default_model_path() -> Optional[Path]:
    from . import utils
    candidate = utils.MODELS / REALESRGAN_MODELS[DEFAULT_MODEL]["file"]
    return candidate if candidate.exists() else None


def _get_upsampler(model_name: str, model_cache: dict):
    """Devuelve el upsampler Real-ESRGAN (cached)."""
    if model_name in model_cache:
        return model_cache[model_name]
    from . import utils
    model_info = REALESRGAN_MODELS[model_name]
    model_path = utils.MODELS / model_info["file"]
    if not model_path.exists():
        raise FileNotFoundError(
            f"Modelo no encontrado: {model_info['file']}. "
            f"Descarga de {model_info['url']}"
        )

    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    if "anime" in model_name:
        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
    else:
        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)

    upsampler = RealESRGANer(
        scale=4,
        model_path=str(model_path),
        model=net,
        tile=512,
        tile_pad=10,
        pre_pad=0,
        half=False,  # CPU-friendly
    )
    model_cache[model_name] = upsampler
    log.info("Real-ESRGAN modelo cargado: %s", model_path.name)
    return upsampler


def _upscale_realesrgan(src: Path, dst: Path, scale: float, target: Optional[str],
                        output_format: str, quality: int, model_cache: dict) -> dict:
    """Usa Real-ESRGAN para reescalar (calidad IA)."""
    if not realesrgan_available():
        raise RuntimeError(
            "Real-ESRGAN no esta disponible. Instala las dependencias y descarga el modelo en models/."
        )

    import numpy as np

    upsampler = _get_upsampler(DEFAULT_MODEL, model_cache)
    img = Image.open(src).convert("RGB")
    w0, h0 = img.size
    w1, h1 = _compute_target_size(w0, h0, scale, target)
    target_scale = max(w1 / w0, h1 / h0)

    arr = np.array(img)
    # Si el target es <= 4x (la capacidad del modelo), una sola pasada.
    # Si el target es > 4x, una pasada IA (4x) + Lanczos al final.
    if target_scale <= upsampler.scale + 0.05:
        out, _ = upsampler.enhance(arr, outscale=upsampler.scale)
        output_img = Image.fromarray(out)
    else:
        out, _ = upsampler.enhance(arr, outscale=upsampler.scale)
        output_img = Image.fromarray(out)
        # Lanczos para alcanzar el target final
        output_img = output_img.resize((w1, h1), resample=Image.LANCZOS)

    if (w1, h1) != output_img.size:
        output_img = output_img.resize((w1, h1), resample=Image.LANCZOS)

    _save_image(output_img, dst, output_format, quality)

    return {
        "path": str(dst),
        "filename": dst.name,
        "filename_original": src.name,
        "width": w1,
        "height": h1,
        "width_original": w0,
        "height_original": h0,
        "scale_factor": round(w1 / w0, 2),
        "method": "realesrgan",
        "size_bytes": dst.stat().st_size,
    }


# -----------------------------------------------------------------------------
# Pre/post-processing
# -----------------------------------------------------------------------------
def _denoise(img: Image.Image, strength: int = 3) -> Image.Image:
    """Denoise suave con Pillow MedianFilter.

    Pillow >= 9.1 usa ImageFilter.MedianFilter; versiones viejas no tienen.
    """
    try:
        median = ImageFilter.MedianFilter
        if hasattr(median, "size"):
            return img.filter(median(size=strength))
        return img.filter(median(strength))
    except Exception:
        return img


def _sharpen(img: Image.Image, radius: float = 1.5, percent: int = 120,
             threshold: int = 2) -> Image.Image:
    """Unsharp mask para realzar bordes tras el reescalado."""
    try:
        return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
    except Exception:
        return img


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _compute_target_size(w0: int, h0: int, scale: float,
                         target: Optional[str]) -> tuple[int, int]:
    """Calcula tamano destino respetando aspect ratio. NUNCA estira.

    Reglas:
      - Si el target es 4K UHD/DCI/QHD/max_4k: la imagen FINAL
        tiene que CABER dentro de esa resolucion (sin pasarse),
        con el mismo aspect ratio que la original.
      - Si el target es un factor (2x/3x/4x): aplica ese factor
        directamente (escalado uniforme, aspect ratio intacto).
    """
    if target and (target in RESOLUTIONS_4K or target == "max_4k"):
        if target == "max_4k":
            tw, th = RESOLUTIONS_4K["4k_uhd"]
        else:
            tw, th = RESOLUTIONS_4K[target]
        # Siempre fit dentro del target, manteniendo aspect ratio.
        # Si la imagen es mas pequena, upscales. Si es mas grande, downscales.
        ratio = min(tw / w0, th / h0)
        return int(w0 * ratio), int(h0 * ratio)
    return int(w0 * scale), int(h0 * scale)


def _save_image(img: Image.Image, dst: Path, output_format: str, quality: int) -> None:
    output_format = output_format.lower()
    if output_format == "jpg" or output_format == "jpeg":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dst, format="JPEG", quality=quality, optimize=True)
    elif output_format == "webp":
        img.save(dst, format="WEBP", quality=quality, method=6)
    else:
        if img.mode == "P":
            img = img.convert("RGBA")
        img.save(dst, format="PNG", optimize=True)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"
