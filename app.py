"""
ImageNinja - Reescalador de imagenes a 4K, 100% local.

Endpoints:
  GET  /              - landing
  GET  /tool/upscale  - herramienta de upscaling
  POST /api/upscale   - reescala una imagen (multipart o json)
  POST /api/info      - devuelve metadata de la imagen
  GET  /outputs/<f>   - descarga de imagen procesada

Arranca con:  python app.py
              http://127.0.0.1:5050
"""
from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Optional

from flask import (
    Flask, abort, jsonify, render_template, request, send_file
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from core import upscaler, utils
from core import metadata as meta_extractor
from core import cleanup as cleanup_module

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = Flask(
    __name__,
    static_folder=str(utils.STATIC),
    template_folder=str(utils.TEMPLATES),
)
app.config["MAX_CONTENT_LENGTH"] = utils.MAX_FILE_SIZE
app.config["JSON_AS_ASCII"] = False
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("imageninja")

# Cache de modelos IA (para que no se recargue cada request)
_MODEL_CACHE: dict = {}


def _resolve_method(requested: str) -> str:
    """Devuelve 'lanczos', 'realesrgan' o 'best' segun lo pedido y disponibilidad."""
    requested = (requested or "best").lower()
    valid = ("lanczos", "realesrgan", "best")
    if requested not in valid:
        requested = "best"
    # Si pide IA (realesrgan o best) y no esta disponible, fallback a Lanczos
    if requested in ("realesrgan", "best") and not upscaler.realesrgan_available():
        log.warning("IA (%s) pedida pero modelo no disponible, fallback a Lanczos", requested)
        return "lanczos"
    return requested


def _save_upload(file_storage) -> Path:
    """Guarda un FileStorage y devuelve la ruta."""
    if not file_storage or not file_storage.filename:
        raise ValueError("Falta el archivo 'file'")
    name = secure_filename(file_storage.filename)
    if not name:
        name = f"upload_{int(time.time() * 1000)}.bin"
    dest = utils.new_upload_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(dest)
    return dest


# -----------------------------------------------------------------------------
# Rutas de pagina
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/tool/upscale")
def tool_upscale():
    return render_template("tool.html", tool=utils.TOOL_INFO["upscale"])


@app.route("/tool/metadata")
def tool_metadata():
    return render_template("tool_metadata.html", tool=utils.TOOL_INFO["metadata"])


@app.route("/outputs/<path:filename>")
def outputs(filename):
    """Sirve archivos generados en outputs/ para descarga directa."""
    safe = (filename or "").replace("\\", "/").lstrip("/")
    full = (utils.OUTPUTS / safe).resolve()
    try:
        full.relative_to(utils.OUTPUTS.resolve())
    except ValueError:
        abort(404)
    if not full.is_file():
        abort(404)
    return send_file(full, as_attachment=True, download_name=full.name)


# -----------------------------------------------------------------------------
# Estado y descarga del modelo
# -----------------------------------------------------------------------------
@app.route("/api/model/status")
def api_model_status():
    """Devuelve el estado actual del modelo IA."""
    return _ok(upscaler.model_status())


@app.route("/api/model/download", methods=["POST"])
def api_model_download():
    """Descarga el modelo IA. Puede tardar varios minutos."""
    try:
        log.info("Iniciando descarga del modelo IA...")
        def _progress(downloaded, total):
            pct = int(downloaded * 100 / total) if total else 0
            log.info("Descarga modelo: %d%% (%d / %d bytes)", pct, downloaded, total)
        path = upscaler.ensure_model(progress_cb=_progress)
        if path is None:
            return _err("No se pudo descargar el modelo", 500)
        return _ok({"ok": True, "path": str(path), "size_mb": round(path.stat().st_size / 1_000_000, 1)})
    except Exception as e:
        log.exception("model download")
        return _err(str(e), 500)


@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    """Borra archivos temporales mas viejos de ttl_seconds (default 1h).

    Pensado como debug tool o para que el usuario limpie manualmente.
    En operacion normal, la limpieza corre automaticamente al startup
    y cada 5 minutos.
    """
    try:
        payload = request.get_json(silent=True) or {}
        ttl = int(payload.get("ttl_seconds", 3600))
    except Exception:
        ttl = 3600
    stats = cleanup_module.run_cleanup(utils.USER_BASE, ttl_seconds=ttl, verbose=True)
    return _ok({
        "stats": stats,
        "freed_human": cleanup_module.format_bytes(stats["total_freed_bytes"]),
    })


# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------
@app.route("/api/info", methods=["POST"])
def api_info():
    try:
        if "file" in request.files:
            f = request.files["file"]
            path = _save_upload(f)
        else:
            data = request.get_json(silent=True) or {}
            url = data.get("url")
            if not url:
                return _err("Falta el archivo 'file' o el campo 'url'")
            path = utils.download_to_uploads(url)
        info = upscaler.image_info(path)
        return _ok({"info": info})
    except Exception as e:
        log.exception("info")
        return _err(str(e), 500)


@app.route("/api/metadata", methods=["POST"])
def api_metadata():
    """Extrae todos los metadatos de una imagen (EXIF, XMP, ICC, etc)."""
    try:
        if "file" not in request.files:
            return _err("Falta el archivo 'file'")
        f = request.files["file"]
        path = _save_upload(f)
        meta = meta_extractor.extract_metadata(path)
        return _ok({"metadata": meta, "filename": path.name})
    except Exception as e:
        log.exception("metadata")
        return _err(str(e), 500)


@app.route("/api/upscale", methods=["POST"])
def api_upscale():
    try:
        # ---- Recolectar parametros ----
        if request.content_type and "multipart" in request.content_type:
            files = request.files.getlist("file")
            if not files:
                return _err("Falta el archivo 'file'")
            # Acepta tanto 'method' (API) como 'quality_preset' (UI nueva)
            method = request.form.get("method") or request.form.get("quality_preset") or "best"
            scale = float(request.form.get("scale", "4"))
            target = request.form.get("target", "4k_uhd").lower() or None
            output_format = request.form.get("format", "png").lower()
            quality = int(request.form.get("quality", "95"))
        else:
            data = request.get_json(silent=True) or {}
            files_meta = data.get("files", [])
            if not files_meta:
                return _err("Falta el campo 'files' con la lista de URLs/base64")
            method = data.get("method") or data.get("quality_preset") or "best"
            scale = float(data.get("scale", "4"))
            target = data.get("target") or "4k_uhd"
            output_format = data.get("format", "png").lower()
            quality = int(data.get("quality", "95"))
            # Por simplicidad, este modo acepta solo archivos ya subidos
            files = []
            for f in files_meta:
                path = utils.UPLOADS / f["name"]
                if not path.exists():
                    return _err(f"Archivo no encontrado: {f['name']}")
                files.append(path)
            return _process_files(files, method, scale, target, output_format, quality)

        if not files:
            return _err("No se enviaron archivos")

        # ---- Si son FileStorage, los guardamos primero ----
        paths = [_save_upload(f) for f in files]

        # ---- Si es un solo archivo, devolvemos la imagen directa ----
        if len(paths) == 1:
            return _process_single(paths[0], method, scale, target, output_format, quality)

        # ---- Si son varios, devolvemos un .zip ----
        return _process_files(paths, method, scale, target, output_format, quality)

    except Exception as e:
        log.exception("upscale")
        return _err(str(e), 500)


def _process_single(path: Path, method: str, scale: float, target: Optional[str],
                    output_format: str, quality: int):
    method = _resolve_method(method)
    out_path = utils.new_output_path(path.stem, f".{output_format}")
    info = upscaler.upscale(
        src=path,
        dst=out_path,
        method=method,
        scale=scale,
        target=target,
        output_format=output_format,
        quality=quality,
        model_cache=_MODEL_CACHE,
    )
    return _ok({"files": [info], "method": method})


def _process_files(paths, method, scale, target, output_format, quality):
    method = _resolve_method(method)
    files_info = []
    for p in paths:
        out = utils.new_output_path(p.stem, f".{output_format}")
        info = upscaler.upscale(
            src=p, dst=out, method=method, scale=scale, target=target,
            output_format=output_format, quality=quality, model_cache=_MODEL_CACHE,
        )
        files_info.append(info)

    # Si son varios, devolver .zip
    zip_path = utils.OUTPUTS / f"imageninja_batch_{int(time.time())}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info in files_info:
            zf.write(info["path"], arcname=info["filename"])

    return _send(zip_path, zip_path.name)


# -----------------------------------------------------------------------------
# Helpers de respuesta
# -----------------------------------------------------------------------------
def _ok(data):
    return jsonify({"ok": True, **data})


def _err(msg, code=400):
    return jsonify({"ok": False, "error": str(msg)}), code


def _send(path: Path, download_name: str):
    return send_file(path, as_attachment=True, download_name=download_name)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def _startup_cleanup() -> None:
    """Limpia archivos temporales viejos al startup y arranca el scheduler."""
    try:
        cleanup_module.run_cleanup(utils.USER_BASE, ttl_seconds=3600, verbose=True)
    except Exception as e:
        log.warning("Limpieza inicial fallo: %s", e)
    try:
        cleanup_module.start_scheduler(utils.USER_BASE, ttl_seconds=3600, interval=300)
    except Exception as e:
        log.warning("No se pudo arrancar el scheduler de limpieza: %s", e)


if __name__ == "__main__":
    log.info("ImageNinja iniciando en http://127.0.0.1:5050")
    _startup_cleanup()
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
