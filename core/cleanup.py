"""
Limpieza automatica de archivos temporales.

ImageNinja corre 100% local y maneja imagenes privadas. Los archivos que
los usuarios suben y los resultados procesados quedan en disco en `uploads/`
y `outputs/`. Sin limpieza, estos directorios crecen sin limite y exponen
datos privados innecesariamente.

Este modulo:
  - Borra archivos mas viejos de un TTL configurable
  - Borra directorios completos si quedan vacios
  - Se llama al startup de Flask
  - Tambien periodicamente (cada N segundos) por si la app queda abierta
  - Protege archivos que se esten usando actualmente (lock ligero por timestamp)

Por defecto:
  - uploads/ y outputs/: archivos > 1 hora se borran
  - models/: NO se toca (es donde vive el modelo IA descargado)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("imageninja.cleanup")

# TTL por defecto en segundos. 1 hora es suficiente para que el usuario
# descargue sus archivos sin prisa, pero no deja basura permanente.
DEFAULT_TTL_SECONDS = 3600

# Cada cuanto se ejecuta la limpieza automatica (segundos).
# 5 minutos es un buen balance: limpia lo viejo sin gastar I/O.
DEFAULT_INTERVAL_SECONDS = 300

# Patrones de archivos a proteger (no se borran aunque sean viejos)
PROTECTED_PATTERNS = (".gitkeep", ".placeholder")

# Subdirectorios que NO se deben limpiar (modelos IA, etc.)
PROTECTED_DIRS = {"models"}


def _safe_rmtree(path: Path) -> bool:
    """Borra un directorio vacio. Devuelve True si se borro."""
    try:
        # Solo borrar si esta vacio (defensa en profundidad)
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            return True
    except OSError as e:
        log.debug("No se pudo borrar directorio vacio %s: %s", path, e)
    return False


def cleanup_dir(
    directory: Path,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    protected_names: Iterable[str] = PROTECTED_PATTERNS,
) -> dict:
    """Borra archivos mas viejos de ttl_seconds dentro de directory.

    No entra en subdirectorios (a menos que sean nuestros temporales).

    Devuelve un dict con stats: {deleted: int, kept: int, errors: int, freed_bytes: int}.
    """
    stats = {"deleted": 0, "kept": 0, "errors": 0, "freed_bytes": 0}
    if not directory.exists() or not directory.is_dir():
        return stats

    protected_set = set(protected_names)
    now = time.time()
    cutoff = now - ttl_seconds

    try:
        entries = list(directory.iterdir())
    except OSError as e:
        log.warning("No se pudo listar %s: %s", directory, e)
        stats["errors"] += 1
        return stats

    for entry in entries:
        # No tocar archivos protegidos (.gitkeep, etc.)
        if entry.name in protected_set:
            stats["kept"] += 1
            continue

        try:
            if not entry.is_file():
                # Si es un subdirectorio, ver si se puede borrar vacio
                if entry.is_dir() and not any(entry.iterdir()):
                    if _safe_rmtree(entry):
                        log.debug("Borrado directorio vacio: %s", entry)
                continue

            # Solo borrar archivos (no symlinks raros)
            stat = entry.stat()
            if stat.st_mtime < cutoff:
                size = stat.st_size
                entry.unlink()
                stats["deleted"] += 1
                stats["freed_bytes"] += size
                log.debug("Borrado archivo viejo: %s (%d B)", entry.name, size)
            else:
                stats["kept"] += 1
        except OSError as e:
            log.debug("Error procesando %s: %s", entry, e)
            stats["errors"] += 1

    return stats


def cleanup_all(
    base_dir: Path,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict:
    """Limpia uploads/ y outputs/. NO toca models/.

    Devuelve stats agregadas: {"uploads": {...}, "outputs": {...}, "total_freed_bytes": int}
    """
    result = {
        "uploads": cleanup_dir(base_dir / "uploads", ttl_seconds),
        "outputs": cleanup_dir(base_dir / "outputs", ttl_seconds),
        "total_freed_bytes": 0,
    }
    result["total_freed_bytes"] = (
        result["uploads"]["freed_bytes"] + result["outputs"]["freed_bytes"]
    )
    return result


def format_bytes(n: int) -> str:
    """Formatea bytes como '1.2 MB'."""
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def run_cleanup(
    base_dir: Path,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    verbose: bool = True,
) -> dict:
    """Wrapper que corre cleanup_all y loguea el resultado.

    Usado por Flask al startup.
    """
    stats = cleanup_all(base_dir, ttl_seconds)
    if verbose and (stats["total_freed_bytes"] > 0 or stats["uploads"]["deleted"] + stats["outputs"]["deleted"] > 0):
        log.info(
            "Limpieza: borrados %d archivos (uploads=%d, outputs=%d), liberados %s",
            stats["uploads"]["deleted"] + stats["outputs"]["deleted"],
            stats["uploads"]["deleted"],
            stats["outputs"]["deleted"],
            format_bytes(stats["total_freed_bytes"]),
        )
    return stats


# -----------------------------------------------------------------------------
# Scheduler: corre la limpieza periodicamente en un hilo daemon
# -----------------------------------------------------------------------------
import threading

_scheduler: Optional[threading.Timer] = None
_scheduler_lock = threading.Lock()


def _scheduler_callback(base_dir: Path, ttl_seconds: int, interval: int) -> None:
    """Callback que ejecuta la limpieza y reprograma el siguiente tick."""
    global _scheduler
    try:
        run_cleanup(base_dir, ttl_seconds, verbose=True)
    except Exception as e:
        log.warning("Limpieza periodica fallo: %s", e)
    finally:
        # Reprogramar
        with _scheduler_lock:
            if _scheduler is not None and _scheduler.is_alive() is False:
                _scheduler = None
            start_scheduler(base_dir, ttl_seconds, interval)


def start_scheduler(
    base_dir: Path,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    interval: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Arranca el scheduler periodico en un hilo daemon.

    Llamar solo una vez al startup. thread.is_alive() se usa para evitar
    multiples schedulers.
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.is_alive():
            log.debug("Limpieza periodica ya activa")
            return
        _scheduler = threading.Timer(
            interval,
            _scheduler_callback,
            args=(base_dir, ttl_seconds, interval),
        )
        _scheduler.daemon = True
        _scheduler.name = "imageninja-cleanup"
        _scheduler.start()
        log.info(
            "Limpieza periodica arrancada: TTL=%ds, cada %ds",
            ttl_seconds,
            interval,
        )


def stop_scheduler() -> None:
    """Detiene el scheduler. Util al cerrar la app (tests)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.cancel()
            _scheduler = None
