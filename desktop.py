"""
ImageNinja - Lanzador de escritorio (pywebview).

Abre la app en una ventana nativa con WebView. No depende del navegador.
Pensado para el ejecutable empaquetado con PyInstaller.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# -----------------------------------------------------------------------------
# Logging temprano (antes de pywebview)
# -----------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Ejecutable PyInstaller
    BASE = Path(sys.executable).resolve().parent
    LOG_PATH = BASE / "imageninja.log"
else:
    BASE = Path(__file__).resolve().parent
    LOG_PATH = BASE / "imageninja.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("imageninja.desktop")


# -----------------------------------------------------------------------------
# Puerto libre
# -----------------------------------------------------------------------------
def _find_free_port(preferred: int = 5050) -> int:
    """Devuelve un puerto TCP libre. Prueba preferred primero."""
    for port in (preferred, 5051, 5052, 5053, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return 0


# -----------------------------------------------------------------------------
# Server en hilo aparte
# -----------------------------------------------------------------------------
def _start_server(port: int) -> threading.Thread:
    """Arranca Flask en un hilo daemon."""
    from app import app  # import local para que el path ya este listo
    log.info("ImageNinja server arrancando en puerto %d", port)

    def _run():
        # threaded=True ya esta en app.run, pero nos aseguramos
        app.run(host="127.0.0.1", port=port, debug=False,
                 use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True, name="flask-server")
    t.start()
    return t


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Espera a que el server responda."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    port = _find_free_port(5050)
    log.info("ImageNinja v1.0.0 - puerto elegido: %d", port)

    server_thread = _start_server(port)
    if not _wait_for_server(port, timeout=15):
        log.error("El server no respondio. Abriendo navegador como fallback.")
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
        return 1

    url = f"http://127.0.0.1:{port}"
    log.info("Abriendo ventana nativa: %s", url)

    try:
        import webview
    except ImportError:
        log.error("pywebview no esta instalado. Abriendo navegador por defecto.")
        webbrowser.open(url)
        return 1

    window = webview.create_window(
        title="ImageNinja",
        url=url,
        width=1280,
        height=820,
        resizable=True,
        maximized=True,
        background_color="#0A0E1A",
        text_select=True,
    )

    # icons: opcional, lo busca relativo al ejecutable
    icon_path = BASE / "static" / "favicon.ico"
    if not icon_path.exists():
        icon_path = None

    webview.start(icon=str(icon_path) if icon_path else None)
    log.info("Ventana cerrada. Saliendo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
